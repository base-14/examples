from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import replace
from typing import Protocol

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings
from temporalio import activity

from kyc_onboarding.attributes import ACTIVITY_ATTEMPT_ATTRIBUTE, CASE_ID_ATTRIBUTE
from kyc_onboarding.models.enums import CaseFault


MODEL_UNAVAILABLE_MAX_ATTEMPT = 2
SANCTIONS_DOWN_MAX_ATTEMPT = 3
MODEL_UNAVAILABLE_HEARTBEAT = "model_unavailable_injected"


class FaultRegistry(Protocol):
    """The technical fault configured for a case, keyed by case ID."""

    def fault_for(self, case_id: str) -> CaseFault | None: ...

    def consume_once(self, case_id: str, fault: CaseFault) -> bool:
        """Claim the one firing of `fault` for `case_id`. True only for the first call per
        pair, concurrent calls included."""
        ...

    def record_fault(self, case_id: str, fault: CaseFault) -> None:
        """Write the fault the API chose for a case. Called from the API only."""
        ...


class StaticFaultRegistry:
    """An in-memory `FaultRegistry`, for tests and for runs with faults disabled."""

    def __init__(self, faults: Mapping[str, CaseFault] | None = None) -> None:
        self._faults = dict(faults or {})
        self._consumed: set[tuple[str, CaseFault]] = set()

    def fault_for(self, case_id: str) -> CaseFault | None:
        return self._faults.get(case_id)

    def consume_once(self, case_id: str, fault: CaseFault) -> bool:
        key = (case_id, fault)
        if key in self._consumed:
            return False
        self._consumed.add(key)
        return True

    def record_fault(self, case_id: str, fault: CaseFault) -> None:
        self._faults[case_id] = fault


class PostgresFaultRegistry:
    """Reads and claims faults in `case_faults`. Every connection carries a `connect_timeout`
    so a stalled Postgres fails instead of hanging the calling thread."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def fault_for(self, case_id: str) -> CaseFault | None:
        import psycopg

        with (
            psycopg.connect(self._dsn, connect_timeout=5) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT fault FROM case_faults WHERE case_id = %s ORDER BY fault LIMIT 1",
                (case_id,),
            )
            row = cursor.fetchone()
        return CaseFault(row[0]) if row else None

    def consume_once(self, case_id: str, fault: CaseFault) -> bool:
        """One `UPDATE ... RETURNING`, so two concurrent attempts never both claim the fault."""
        import psycopg

        with (
            psycopg.connect(self._dsn, connect_timeout=5) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE case_faults SET consumed = TRUE "
                "WHERE case_id = %s AND fault = %s AND NOT consumed "
                "RETURNING case_id",
                (case_id, fault.value),
            )
            row = cursor.fetchone()
        return row is not None

    def record_fault(self, case_id: str, fault: CaseFault) -> None:
        """`ON CONFLICT DO NOTHING` keeps a retried API request idempotent."""
        import psycopg

        with (
            psycopg.connect(self._dsn, connect_timeout=5) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "INSERT INTO case_faults (case_id, fault) VALUES (%s, %s) "
                "ON CONFLICT (case_id, fault) DO NOTHING",
                (case_id, fault.value),
            )


def log_injected_fault(fault: CaseFault, info: activity.Info) -> None:
    activity.logger.error(
        f"injected {fault.value} fault",
        extra={
            CASE_ID_ATTRIBUTE: info.workflow_id,
            ACTIVITY_ATTEMPT_ATTRIBUTE: info.attempt,
        },
    )


def should_raise_model_unavailable(fault: CaseFault | None, attempt: int) -> bool:
    return fault == CaseFault.model_unavailable and attempt <= MODEL_UNAVAILABLE_MAX_ATTEMPT


def should_raise_sanctions_down(fault: CaseFault | None, attempt: int) -> bool:
    return fault == CaseFault.sanctions_down and attempt <= SANCTIONS_DOWN_MAX_ATTEMPT


def has_retry_prompt(messages: list[ModelMessage]) -> bool:
    """True once Pydantic AI has rejected a response and asked the model again."""
    return any(
        getattr(part, "part_kind", None) == "retry-prompt"
        for message in messages
        for part in getattr(message, "parts", ())
    )


def corrupt_response(response: ModelResponse) -> ModelResponse:
    """Turn each tool call into its arguments as plain text, the way a small model sometimes
    answers instead of calling the tool. Pydantic AI rejects the text and asks again."""
    text_parts = [
        TextPart(content=part.args_as_json_str()) if isinstance(part, ToolCallPart) else part
        for part in response.parts
        if isinstance(part, ToolCallPart | TextPart)
    ]
    return replace(response, parts=text_parts)


class FaultInjectingModel(WrapperModel):
    """Injects `model_unavailable` and `bad_output` inside a model-request activity, and
    passes requests through outside one.

    The activity has no run context, so the case's fault is looked up in a `FaultRegistry` by
    `activity.info().workflow_id`. `sanctions_down` is injected in the `screen_sanctions`
    tool instead, which has `ctx.deps.fault`.

    Each fault fires once per case, claimed through `consume_once`. `bad_output` fires only
    when `injects_bad_output` is set, so only the extraction model corrupts a response.
    Registry calls block on Postgres and run in `asyncio.to_thread`. `activity.info()` is
    read first because it comes from a context var scoped to the activity's task.
    """

    def __init__(
        self, wrapped: Model, *, faults: FaultRegistry, injects_bad_output: bool = True
    ) -> None:
        super().__init__(wrapped)
        self._faults = faults
        self._injects_bad_output = injects_bad_output

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        if not activity.in_activity():
            return await super().request(messages, model_settings, model_request_parameters)

        info = activity.info()
        # `workflow_id` is typed `str | None`; without one there is no case to look up.
        case_id = info.workflow_id
        fault = (
            await asyncio.to_thread(self._faults.fault_for, case_id)
            if case_id is not None
            else None
        )

        if await self._fires_model_unavailable(fault, info):
            log_injected_fault(CaseFault.model_unavailable, info)
            activity.heartbeat(MODEL_UNAVAILABLE_HEARTBEAT)
            raise ConnectionError(f"ollama unreachable (attempt {info.attempt})")

        response = await super().request(messages, model_settings, model_request_parameters)

        fires_bad_output = (
            self._injects_bad_output
            and fault == CaseFault.bad_output
            and case_id is not None
            and not has_retry_prompt(messages)
            and await asyncio.to_thread(self._faults.consume_once, case_id, CaseFault.bad_output)
        )
        if fires_bad_output:
            log_injected_fault(CaseFault.bad_output, info)
            return corrupt_response(response)

        return response

    async def _fires_model_unavailable(self, fault: CaseFault | None, info: activity.Info) -> bool:
        """Attempt 1 claims the fault and leaves a heartbeat marker. Later attempts fire only
        when they carry it, so no other model activity fails."""
        if info.workflow_id is None or not should_raise_model_unavailable(fault, info.attempt):
            return False
        if info.attempt == 1:
            return await asyncio.to_thread(
                self._faults.consume_once, info.workflow_id, CaseFault.model_unavailable
            )
        return MODEL_UNAVAILABLE_HEARTBEAT in info.heartbeat_details
