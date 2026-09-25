"""The API routes and their error codes, against a time-skipping environment and scripted models."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import TYPE_CHECKING

import httpx2 as httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.trace import SpanKind

from kyc_onboarding import main
from kyc_onboarding.agents import FaultRegistry, StaticFaultRegistry
from kyc_onboarding.attributes import (
    ACCOUNT_TYPE_ATTRIBUTE,
    CASE_ID_ATTRIBUTE,
    DOCUMENT_TYPE_ATTRIBUTE,
    HTTP_STATUS_CODE_ATTRIBUTE,
    REVIEW_DECISION_ATTRIBUTE,
)
from kyc_onboarding.models.decisions import EscalateDecision
from kyc_onboarding.models.enums import AccountType, CaseFault, DocumentType, RiskLevel
from kyc_onboarding.worker import create_worker
from tests._telemetry_support import captured_logs, captured_spans, log_attribute, log_body
from tests._workflow_support import (
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    time_skipping_env,
)


if TYPE_CHECKING:
    from kyc_onboarding.case_agents import CaseAgents


client = TestClient(main.app)

# The worker must poll the queue `create_case` starts workflows on, or every wait hangs.
TASK_QUEUE = main.settings.temporal_task_queue

PARTIAL_SANCTIONS_MATCH = EscalateDecision(
    risk_level=RiskLevel.medium, reasons=["partial sanctions match"]
)

OVERRIDES_REFUSED_DETAIL = "fault and deadline/budget overrides require KYC_FAULTS_ENABLED=true"

pytestmark = pytest.mark.usefixtures("sanctions_clear")


def test_health_returns_the_api_fallback_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "service": "ai-kyc-onboarding-api"}


def test_health_returns_otel_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "kyc-api-from-env")

    response = client.get("/health")

    assert response.json() == {"status": "healthy", "service": "kyc-api-from-env"}


class RecordingFaultRegistry(StaticFaultRegistry):
    """Logs each `record_fault` call to a shared call list to check its order."""

    def __init__(self, calls: list[str]) -> None:
        super().__init__()
        self.recorded: list[tuple[str, CaseFault]] = []
        self._calls = calls

    def record_fault(self, case_id: str, fault: CaseFault) -> None:
        self._calls.append("record_fault")
        self.recorded.append((case_id, fault))
        super().record_fault(case_id, fault)


@asynccontextmanager
async def api_client(
    agents: CaseAgents, *, fault_registry: FaultRegistry | None = None
) -> AsyncIterator[httpx.AsyncClient]:
    """A live app backed by a time-skipping worker, with `app.state` set directly."""
    async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
        main.app.state.temporal_client = env.client
        main.app.state.fault_registry = fault_registry or StaticFaultRegistry()
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api:
            yield api


def _case_body(
    account_type: AccountType = AccountType.personal, **overrides: object
) -> dict[str, object]:
    return {
        "name": "Maria Gonzalez",
        "country": "IE",
        "account_type": account_type.value,
        **overrides,
    }


async def _create_case(api: httpx.AsyncClient, **overrides: object) -> dict[str, object]:
    response = await api.post("/cases", json=_case_body(**overrides))
    assert response.status_code == 201
    return response.json()


async def _submit_document(
    api: httpx.AsyncClient, case_id: str, document_type: DocumentType
) -> httpx.Response:
    return await api.post(
        f"/cases/{case_id}/documents",
        json={"document_type": document_type.value, "raw_text": f"{document_type} text"},
    )


async def _wait_for_status(api: httpx.AsyncClient, case_id: str, status: str) -> dict[str, object]:
    import asyncio

    async with asyncio.timeout(10):
        while True:
            view = (await api.get(f"/cases/{case_id}")).json()
            if view["status"] == status:
                return view
            await asyncio.sleep(0.05)


class TestCreateCase:
    async def test_starts_a_workflow_and_returns_the_initial_status(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)

        assert created["status"] == "awaiting_documents"
        assert created["missing_documents"] == ["id", "proof_of_address"]
        assert created["resubmission_round"] == 0
        assert created["decisions"] == []
        assert created["outcome"] is None
        assert created["escalation_reason"] is None

    async def test_business_account_also_requires_the_registration_certificate(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api, account_type=AccountType.business)

        assert created["missing_documents"] == [
            "id",
            "proof_of_address",
            "registration_certificate",
        ]

    async def test_malformed_body_returns_422(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.post("/cases", json={"name": "Maria Gonzalez"})

        assert response.status_code == 422
        missing = {tuple(error["loc"]) for error in response.json()["detail"]}
        assert missing == {("body", "country"), ("body", "account_type")}

    async def test_refuses_a_fault_when_faults_are_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "settings", replace(main.settings, faults_enabled=False))
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.post(
                "/cases", json=_case_body(fault=CaseFault.model_unavailable.value)
            )

        assert response.status_code == 422
        assert response.json() == {"detail": OVERRIDES_REFUSED_DETAIL}

    async def test_refuses_a_deadline_override_when_faults_are_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "settings", replace(main.settings, faults_enabled=False))
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.post("/cases", json=_case_body(document_deadline_seconds=5))

        assert response.status_code == 422
        assert response.json() == {"detail": OVERRIDES_REFUSED_DETAIL}

    async def test_refuses_a_budget_override_when_faults_are_disabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "settings", replace(main.settings, faults_enabled=False))
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.post("/cases", json=_case_body(request_budget=1))

        assert response.status_code == 422
        assert response.json() == {"detail": OVERRIDES_REFUSED_DETAIL}

    async def test_accepts_and_records_a_fault_when_faults_are_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "settings", replace(main.settings, faults_enabled=True))
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        calls: list[str] = []
        registry = RecordingFaultRegistry(calls)
        async with api_client(agents, fault_registry=registry) as api:
            temporal_client = main.app.state.temporal_client
            start_workflow = temporal_client.start_workflow

            async def recording_start_workflow(*args: object, **kwargs: object) -> object:
                calls.append("start_workflow")
                return await start_workflow(*args, **kwargs)

            monkeypatch.setattr(temporal_client, "start_workflow", recording_start_workflow)
            created = await _create_case(api, fault=CaseFault.model_unavailable.value)

        assert registry.recorded == [(created["case_id"], CaseFault.model_unavailable)]
        assert calls == ["record_fault", "start_workflow"]

    async def test_tight_budget_fault_escalates_with_empty_decisions(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(main, "settings", replace(main.settings, faults_enabled=True))
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api, fault=CaseFault.tight_budget.value)
            case_id = created["case_id"]
            await _submit_document(api, case_id, DocumentType.id)
            await _submit_document(api, case_id, DocumentType.proof_of_address)
            in_review = await _wait_for_status(api, case_id, "awaiting_review")

        assert in_review["escalation_reason"] == "budget"
        assert in_review["decisions"] == []


class TestSubmitDocument:
    async def test_returns_404_for_an_unknown_case(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await _submit_document(api, "no-such-case", DocumentType.id)

        assert response.status_code == 404

    async def test_returns_409_once_the_case_is_closed(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)
            case_id = created["case_id"]
            await _submit_document(api, case_id, DocumentType.id)
            await _submit_document(api, case_id, DocumentType.proof_of_address)
            await _wait_for_status(api, case_id, "approved")

            response = await _submit_document(api, case_id, DocumentType.id)

        assert response.status_code == 409
        assert response.json() == {"detail": "case is closed"}

    async def test_accepted_and_progresses_the_case_to_approval(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)
            case_id = created["case_id"]

            first = await _submit_document(api, case_id, DocumentType.id)
            assert first.status_code == 202
            assert first.json() == {"case_id": case_id, "document_type": "id"}

            second = await _submit_document(api, case_id, DocumentType.proof_of_address)
            assert second.status_code == 202

            approved = await _wait_for_status(api, case_id, "approved")

        assert approved["outcome"] == "approved"
        assert approved["decisions"] == [{"decision": "approve"}]


class TestGetCase:
    async def test_returns_404_for_an_unknown_case(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.get("/cases/no-such-case")

        assert response.status_code == 404

    async def test_returns_the_current_status(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)
            response = await api.get(f"/cases/{created['case_id']}")

        assert response.status_code == 200
        assert response.json() == created


class TestSubmitReview:
    async def test_returns_404_for_an_unknown_case(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            response = await api.post(
                "/cases/no-such-case/review", json={"decision": "approve", "reviewer": "r.okafor"}
            )

        assert response.status_code == 404

    async def test_returns_409_while_the_case_is_not_awaiting_review(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)
            response = await api.post(
                f"/cases/{created['case_id']}/review",
                json={"decision": "approve", "reviewer": "r.okafor"},
            )

        assert response.status_code == 409
        assert response.json() == {"detail": "case is awaiting_documents, not awaiting a review"}

    async def test_returns_409_for_a_second_review_while_the_first_is_pending(self) -> None:
        import asyncio

        agents = build_test_agents(
            ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
        )
        async with api_client(agents) as api:
            created = await _create_case(api)
            case_id = created["case_id"]
            await _submit_document(api, case_id, DocumentType.id)
            await _submit_document(api, case_id, DocumentType.proof_of_address)
            await _wait_for_status(api, case_id, "awaiting_review")

            first, second = await asyncio.gather(
                api.post(
                    f"/cases/{case_id}/review",
                    json={"decision": "approve", "reviewer": "r.okafor"},
                ),
                api.post(
                    f"/cases/{case_id}/review",
                    json={"decision": "reject", "reviewer": "a.lindqvist"},
                ),
            )

        by_status = {response.status_code: response for response in (first, second)}
        assert sorted(by_status) == [200, 409]
        assert by_status[409].json() == {"detail": "case is awaiting_review, not awaiting a review"}

    async def test_returns_404_once_the_case_is_closed(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        async with api_client(agents) as api:
            created = await _create_case(api)
            case_id = created["case_id"]
            await _submit_document(api, case_id, DocumentType.id)
            await _submit_document(api, case_id, DocumentType.proof_of_address)
            await _wait_for_status(api, case_id, "approved")

            response = await api.post(
                f"/cases/{case_id}/review", json={"decision": "approve", "reviewer": "r.okafor"}
            )

        assert response.status_code == 404

    async def test_accepted_review_closes_the_case_and_surfaces_the_escalation_reason(
        self,
    ) -> None:
        agents = build_test_agents(
            ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
        )
        async with api_client(agents) as api:
            created = await _create_case(api)
            case_id = created["case_id"]
            await _submit_document(api, case_id, DocumentType.id)
            await _submit_document(api, case_id, DocumentType.proof_of_address)
            await _wait_for_status(api, case_id, "awaiting_review")

            response = await api.post(
                f"/cases/{case_id}/review",
                json={"decision": "approve", "reviewer": "r.okafor"},
            )

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "approved"
        assert body["escalation_reason"] == "risk"
        assert body["review"] == {"decision": "approve", "reviewer": "r.okafor", "note": None}
        assert body["decisions"] == [
            {
                "decision": "escalate",
                "risk_level": "medium",
                "reasons": ["partial sanctions match"],
            }
        ]


class TestRequestLogs:
    async def test_accepted_requests_log_the_case_story_at_info(self) -> None:
        agents = build_test_agents(
            ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
        )
        with captured_logs() as logs:
            async with api_client(agents) as api:
                created = await _create_case(api)
                case_id = str(created["case_id"])
                await _submit_document(api, case_id, DocumentType.id)
                await _submit_document(api, case_id, DocumentType.proof_of_address)
                await _wait_for_status(api, case_id, "awaiting_review")
                await api.post(
                    f"/cases/{case_id}/review",
                    json={"decision": "approve", "reviewer": "r.okafor"},
                )
            api_lines = [
                record
                for record in logs.get_finished_logs()
                if record.instrumentation_scope is not None
                and record.instrumentation_scope.name == main.__name__
                and log_attribute(record, CASE_ID_ATTRIBUTE) == case_id
            ]

        assert [log_body(record) for record in api_lines] == [
            "case created",
            "document accepted",
            "document accepted",
            "review accepted",
        ]
        assert {record.log_record.severity_text for record in api_lines} == {"INFO"}
        assert all(record.log_record.trace_id for record in api_lines)
        assert len({record.log_record.trace_id for record in api_lines}) == len(api_lines)

    async def test_refused_requests_log_a_warning_with_the_status_code(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        with captured_logs() as logs:
            async with api_client(agents) as api:
                await api.post("/cases", json={"name": "Maria Gonzalez"})
                await _submit_document(api, "no-such-case", DocumentType.id)
                created = await _create_case(api)
                await api.post(
                    f"/cases/{created['case_id']}/review",
                    json={"decision": "approve", "reviewer": "r.okafor"},
                )
            refusals = [
                record
                for record in logs.get_finished_logs()
                if log_body(record).startswith("request refused")
            ]

        assert [
            (
                log_attribute(record, HTTP_STATUS_CODE_ATTRIBUTE),
                log_attribute(record, CASE_ID_ATTRIBUTE),
            )
            for record in refusals
        ] == [(422, None), (404, "no-such-case"), (409, created["case_id"])]
        assert {record.log_record.severity_text for record in refusals} == {"WARN"}
        assert log_body(refusals[1]) == (
            "request refused: POST /cases/no-such-case/documents returned 404, case not found"
        )


def _server_spans(spans: list[ReadableSpan], name: str) -> list[dict[str, object]]:
    return [
        dict(span.attributes or {})
        for span in spans
        if span.kind == SpanKind.SERVER and span.name == name
    ]


class TestRequestSpans:
    async def test_accepted_requests_put_the_case_and_business_key_on_the_server_span(
        self,
    ) -> None:
        agents = build_test_agents(
            ScriptedExtraction(), ScriptedAssessment(decisions=[PARTIAL_SANCTIONS_MATCH])
        )
        with captured_spans() as exporter:
            async with api_client(agents) as api:
                created = await _create_case(api, account_type=AccountType.personal)
                case_id = str(created["case_id"])
                await _submit_document(api, case_id, DocumentType.id)
                await _submit_document(api, case_id, DocumentType.proof_of_address)
                await _wait_for_status(api, case_id, "awaiting_review")
                await api.post(
                    f"/cases/{case_id}/review",
                    json={"decision": "reject", "reviewer": "r.okafor"},
                )
            spans = list(exporter.get_finished_spans())

        (create,) = _server_spans(spans, "POST /cases")
        documents = _server_spans(spans, "POST /cases/{case_id}/documents")
        (review,) = _server_spans(spans, "POST /cases/{case_id}/review")
        status_reads = _server_spans(spans, "GET /cases/{case_id}")
        assert status_reads
        assert {read[CASE_ID_ATTRIBUTE] for read in status_reads} == {case_id}
        assert (create[CASE_ID_ATTRIBUTE], create[ACCOUNT_TYPE_ATTRIBUTE]) == (case_id, "personal")
        assert [(d[CASE_ID_ATTRIBUTE], d[DOCUMENT_TYPE_ATTRIBUTE]) for d in documents] == [
            (case_id, "id"),
            (case_id, "proof_of_address"),
        ]
        assert (review[CASE_ID_ATTRIBUTE], review[REVIEW_DECISION_ATTRIBUTE]) == (
            case_id,
            "reject",
        )

    async def test_refused_requests_carry_the_case_id_from_the_path(self) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        with captured_spans() as exporter:
            async with api_client(agents) as api:
                await api.post("/cases", json={"name": "Maria Gonzalez"})
                await _submit_document(api, "no-such-case", DocumentType.id)
            spans = list(exporter.get_finished_spans())

        (refused_create,) = _server_spans(spans, "POST /cases")
        (refused_document,) = _server_spans(spans, "POST /cases/{case_id}/documents")
        assert CASE_ID_ATTRIBUTE not in refused_create
        assert refused_document[CASE_ID_ATTRIBUTE] == "no-such-case"
        assert refused_document[DOCUMENT_TYPE_ATTRIBUTE] == "id"

    async def test_a_body_refused_before_the_handler_runs_still_carries_the_case_id(
        self,
    ) -> None:
        agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment())
        with captured_spans() as exporter:
            async with api_client(agents) as api:
                response = await api.post(
                    "/cases/some-case/review", json={"decision": "maybe", "reviewer": "r.okafor"}
                )
            spans = list(exporter.get_finished_spans())

        assert response.status_code == 422
        (refused_review,) = _server_spans(spans, "POST /cases/{case_id}/review")
        assert refused_review[CASE_ID_ATTRIBUTE] == "some-case"
        assert REVIEW_DECISION_ATTRIBUTE not in refused_review
