import json
from datetime import date

import pytest
from openai import omit
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.chat.chat_completion_message_function_tool_call import (
    ChatCompletionMessageFunctionToolCall,
    Function,
)
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kyc_onboarding.agents.assessment import (
    DECISION_SCHEMA_TEMPLATE,
    MISSING_EXPIRY_RETRY,
    build_assessment_agent,
)
from kyc_onboarding.agents.deps import AssessmentDeps
from kyc_onboarding.agents.extraction import OUTPUT_RETRIES
from kyc_onboarding.agents.faults import StaticFaultRegistry
from kyc_onboarding.models.decisions import (
    ApproveDecision,
    EscalateDecision,
    RequestResubmissionDecision,
)
from kyc_onboarding.models.enums import DocumentType, RiskLevel
from kyc_onboarding.tools import ExpiryCheck, IdentityCheck, SanctionsScreeningResult
from tests._workflow_support import VALID_EXPIRY_DATE, check_calls, decision_answer


pytestmark = pytest.mark.usefixtures("sanctions_clear")


def _build_agent() -> object:
    return build_assessment_agent(
        instructions="assess the case",
        base_url="http://localhost:11434",
        model_name="unused-in-tests",
        faults=StaticFaultRegistry(),
    )


def _last_tool_return(messages: list[ModelMessage]) -> object:
    last_request = messages[-1]
    part = last_request.parts[-1]
    assert isinstance(part, ToolReturnPart)
    return part.content


class TestBuildAssessmentAgent:
    async def test_calls_check_expiry_then_approves(self) -> None:
        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(tool_name="check_expiry", args={"expiry_date": VALID_EXPIRY_DATE})
                )
            expiry_check = _last_tool_return(messages)
            assert isinstance(expiry_check, ExpiryCheck)
            assert expiry_check.status == "valid"
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()

    async def test_check_expiry_uses_the_deps_reference_date(self) -> None:
        seen_expiry_checks: list[ExpiryCheck] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(tool_name="check_expiry", args={"expiry_date": "2020-01-01"})
                )
            expiry_check = _last_tool_return(messages)
            assert isinstance(expiry_check, ExpiryCheck)
            seen_expiry_checks.append(expiry_check)
            return decision_answer(
                RequestResubmissionDecision(
                    reasons=["expired id"], documents_to_resend=[DocumentType.id]
                )
            )

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert seen_expiry_checks == [
            ExpiryCheck(
                status="expired",
                expired=True,
                expiry_date=date(2020, 1, 1),
                reference_date=date(2026, 1, 1),
            )
        ]
        assert isinstance(result.output, RequestResubmissionDecision)

    async def test_an_approval_after_a_missing_expiry_date_is_asked_again(self) -> None:
        retry_prompts: list[str] = []
        resend_id = RequestResubmissionDecision(
            reasons=["the ID's expiry date is missing"], documents_to_resend=[DocumentType.id]
        )
        replies = iter([decision_answer(ApproveDecision()), decision_answer(resend_id)])

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(tool_name="check_expiry", args={"expiry_date": None})
                )
            retry_prompts.extend(
                str(part.content)
                for part in messages[-1].parts
                if isinstance(part, RetryPromptPart)
            )
            return next(replies)

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == resend_id
        assert retry_prompts == [MISSING_EXPIRY_RETRY]

    async def test_an_escalation_after_a_missing_expiry_date_is_accepted(self) -> None:
        escalation = EscalateDecision(
            risk_level=RiskLevel.medium, reasons=["the ID's expiry date is missing"]
        )

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(tool_name="check_expiry", args={"expiry_date": None})
                )
            return decision_answer(escalation)

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == escalation

    async def test_screen_sanctions_receives_the_deps_dsn(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, str]] = []

        def fake_screen(name: str, dsn: str) -> SanctionsScreeningResult:
            calls.append((name, dsn))
            return SanctionsScreeningResult(result="clear", matched_entry=None, score=None)

        monkeypatch.setattr("kyc_onboarding.agents.tools._screen_sanctions", fake_screen)

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(tool_name="screen_sanctions", args={"name": "Jane Doe"})
                )
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://tenant-x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            await agent.run("assess this case", deps=deps)

        assert calls == [("Jane Doe", "postgresql://tenant-x")]

    async def test_compare_identity_accepts_document_fields_sent_as_json_strings(self) -> None:
        seen_identity_checks: list[IdentityCheck] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls(
                    ToolCallPart(
                        tool_name="compare_identity",
                        args={
                            "id_fields": json.dumps(
                                {
                                    "full_name": "Jane Doe",
                                    "date_of_birth": "1990-01-01",
                                    "id_number": "X1",
                                    "declared_address": "1 Main St",
                                }
                            ),
                            "proof_of_address_fields": json.dumps(
                                {"account_holder": "Jane Doe", "address": "2 Side St"}
                            ),
                        },
                    )
                )
            identity_check = _last_tool_return(messages)
            assert isinstance(identity_check, IdentityCheck)
            seen_identity_checks.append(identity_check)
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            await agent.run("assess this case", deps=deps)

        assert seen_identity_checks == [
            IdentityCheck(match=False, mismatches=["address on id does not match proof_of_address"])
        ]

    async def test_recovers_after_two_prose_answers(self) -> None:
        answers: list[str] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls()
            if len(answers) < 2:
                answers.append("prose")
                return ModelResponse(parts=[TextPart(content="The case looks fine to approve.")])
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()

    async def test_a_decision_before_the_tool_calls_is_asked_again_naming_the_missing_tools(
        self,
    ) -> None:
        retry_prompts: list[str] = []
        replies = iter(
            [
                decision_answer(ApproveDecision()),
                ModelResponse(
                    parts=[
                        ToolCallPart(
                            tool_name="check_expiry", args={"expiry_date": VALID_EXPIRY_DATE}
                        ),
                        ToolCallPart(tool_name="screen_sanctions", args={"name": "Jane Doe"}),
                    ]
                ),
                decision_answer(ApproveDecision()),
                ModelResponse(parts=[ToolCallPart(tool_name="compare_identity", args={})]),
                decision_answer(ApproveDecision()),
            ]
        )

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            retry_prompts.extend(
                str(part.content)
                for part in messages[-1].parts
                if isinstance(part, RetryPromptPart)
            )
            return next(replies)

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()
        assert retry_prompts == [
            "Before deciding, call the tools that have not returned a result yet: "
            "check_expiry, compare_identity, screen_sanctions.",
            "Before deciding, call the tools that have not returned a result yet: "
            "compare_identity.",
        ]

    async def test_a_decision_never_preceded_by_the_tool_calls_fails(self) -> None:
        requests: list[int] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            requests.append(len(messages))
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with (
            agent.override(model=FunctionModel(respond)),
            pytest.raises(UnexpectedModelBehavior, match="Exceeded maximum output retries"),
        ):
            await agent.run("assess this case", deps=deps)

        assert len(requests) == 1 + OUTPUT_RETRIES

    async def test_accepts_an_analysis_followed_by_the_decision_in_a_json_code_block(
        self,
    ) -> None:
        decision = decision_answer(ApproveDecision()).text

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls()
            answer = f"Every check passed, so I approve.\n\n```json\n{decision}\n```"
            return ModelResponse(parts=[TextPart(content=answer)])

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()

    @pytest.mark.parametrize(
        "first_answer",
        [
            {"decision": "reject"},
            {"decision": "escalate", "reasons": ["partial sanctions match"]},
            {"decision": "escalate", "reasons": [], "risk_level": "medium"},
            {"decision": "request_resubmission", "documents_to_resend": ["id"]},
        ],
        ids=[
            "unknown decision",
            "escalation without a risk level",
            "escalation without a reason",
            "resubmission without a reason",
        ],
    )
    async def test_an_answer_that_names_no_valid_decision_is_asked_again(
        self, first_answer: dict[str, object]
    ) -> None:
        retry_prompts: list[str] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls()
            retry_prompts.extend(
                str(part.content)
                for part in messages[-1].parts
                if isinstance(part, RetryPromptPart)
            )
            if not retry_prompts:
                return ModelResponse(parts=[TextPart(content=json.dumps(first_answer))])
            return decision_answer(ApproveDecision())

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()
        assert len(retry_prompts) == 1

    async def test_an_escalation_answer_becomes_an_escalate_decision(self) -> None:
        answer = {
            "decision": "escalate",
            "reasons": ["partial sanctions match"],
            "documents_to_resend": [],
            "risk_level": "medium",
        }

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(messages) == 1:
                return check_calls()
            return ModelResponse(parts=[TextPart(content=json.dumps(answer))])

        agent = _build_agent()
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("assess this case", deps=deps)

        assert result.output == EscalateDecision(
            risk_level=RiskLevel.medium, reasons=["partial sanctions match"]
        )

    async def test_offers_its_tools_and_asks_for_the_decision_as_json_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "kyc_onboarding.agents.tools._screen_sanctions",
            lambda *_a, **_k: SanctionsScreeningResult(
                result="clear", matched_entry=None, score=None
            ),
        )
        requests: list[dict[str, object]] = []
        replies = [
            _chat_completion(
                tool_calls=[
                    ("check_expiry", {"expiry_date": VALID_EXPIRY_DATE}),
                    ("compare_identity", {}),
                    ("screen_sanctions", {"name": "Jane Doe"}),
                ]
            ),
            _chat_completion(content=decision_answer(ApproveDecision()).text),
        ]

        async def create(**kwargs: object) -> ChatCompletion:
            requests.append(kwargs)
            return replies[len(requests) - 1]

        agent = _build_agent()
        model = agent.model.wrapped
        monkeypatch.setattr(model.client.chat.completions, "create", create)
        deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
        result = await agent.run("assess this case", deps=deps)

        assert result.output == ApproveDecision()
        for request in requests:
            assert request["response_format"] is omit
            tool_names = {tool["function"]["name"] for tool in request["tools"]}
            assert tool_names == {"check_expiry", "compare_identity", "screen_sanctions"}
            system = "\n".join(
                message["content"] for message in request["messages"] if message["role"] == "system"
            )
            assert "assess the case" in system
            assert DECISION_SCHEMA_TEMPLATE.split("{schema}")[0] in system
            assert '"documents_to_resend"' in system

    async def test_compare_identity_accepts_registration_certificate_fields_as_a_json_string(
        self,
    ) -> None:
        certificate = {
            "company_name": "Doe Trading Ltd",
            "registration_number": "IE-1",
            "address": "1 Main St",
            "authorized_representative": "Jane Doe",
        }

        reply = await _compare_identity_reply(
            {
                "registration_certificate_fields": json.dumps(certificate),
                "proof_of_address_fields": {"account_holder": "Jane Doe", "address": "2 Side St"},
            }
        )

        assert reply == IdentityCheck(
            match=False,
            mismatches=["address on registration_certificate does not match proof_of_address"],
        )

    async def test_compare_identity_sends_a_non_json_string_back_as_a_validation_retry(
        self,
    ) -> None:
        reply = await _compare_identity_reply({"id_fields": "Jane Doe, born 1990"})

        assert isinstance(reply, RetryPromptPart)
        assert reply.tool_name == "compare_identity"


def _chat_completion(
    *, content: str | None = None, tool_calls: list[tuple[str, dict[str, object]]] | None = None
) -> ChatCompletion:
    calls = (
        [
            ChatCompletionMessageFunctionToolCall(
                id=f"call-{index}",
                type="function",
                function=Function(name=name, arguments=json.dumps(args)),
            )
            for index, (name, args) in enumerate(tool_calls)
        ]
        if tool_calls
        else None
    )
    return ChatCompletion(
        id="chatcmpl-1",
        object="chat.completion",
        created=0,
        model="qwen3.5:9B",
        choices=[
            Choice(
                index=0,
                finish_reason="tool_calls" if calls else "stop",
                message=ChatCompletionMessage(role="assistant", content=content, tool_calls=calls),
            )
        ],
    )


async def _compare_identity_reply(args: dict[str, object]) -> object:
    """The tool's result for `args`, or the retry prompt if they fail validation."""
    replies: list[object] = []

    def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        if len(messages) == 1:
            return check_calls(ToolCallPart(tool_name="compare_identity", args=args))
        if not replies:
            part = messages[-1].parts[-1]
            replies.append(part.content if isinstance(part, ToolReturnPart) else part)
            if isinstance(part, RetryPromptPart):
                return ModelResponse(parts=[ToolCallPart(tool_name="compare_identity", args={})])
        return decision_answer(ApproveDecision())

    agent = _build_agent()
    deps = AssessmentDeps(dsn="postgresql://x", reference_date=date(2026, 1, 1))
    with agent.override(model=FunctionModel(respond)):
        await agent.run("assess this case", deps=deps)

    (reply,) = replies
    return reply
