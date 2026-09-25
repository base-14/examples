from datetime import date

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from kyc_onboarding.agents.extraction import build_extraction_agent
from kyc_onboarding.agents.faults import StaticFaultRegistry
from kyc_onboarding.models.documents import ExtractedIdFields, ExtractedProofOfAddressFields


def _build_agent() -> object:
    return build_extraction_agent(
        instructions="extract the fields from the document",
        base_url="http://localhost:11434",
        model_name="unused-in-tests",
        faults=StaticFaultRegistry(),
    )


def _tool_named(info: AgentInfo, name: str) -> str:
    return next(t.name for t in info.output_tools if t.name == name)


class TestBuildExtractionAgent:
    async def test_parses_a_typed_id_output(self) -> None:
        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            tool_name = _tool_named(info, "final_result_ExtractedIdFields")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=tool_name,
                        args={
                            "full_name": "Jane Doe",
                            "date_of_birth": "1990-01-01",
                            "id_number": "X123",
                        },
                    )
                ]
            )

        agent = _build_agent()
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("some id document text")

        assert result.output == ExtractedIdFields(
            full_name="Jane Doe", date_of_birth=date(1990, 1, 1), id_number="X123"
        )

    async def test_parses_a_typed_proof_of_address_output(self) -> None:
        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            tool_name = _tool_named(info, "final_result_ExtractedProofOfAddressFields")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=tool_name,
                        args={"account_holder": "Jane Doe", "address": "1 Main St"},
                    )
                ]
            )

        agent = _build_agent()
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("some proof of address text")

        assert result.output == ExtractedProofOfAddressFields(
            account_holder="Jane Doe", address="1 Main St"
        )

    async def test_has_no_tools_of_its_own(self) -> None:
        seen: list[list[str]] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            seen.append([t.name for t in info.function_tools])
            tool_name = _tool_named(info, "final_result_ExtractedIdFields")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=tool_name,
                        args={
                            "full_name": "Jane Doe",
                            "date_of_birth": "1990-01-01",
                            "id_number": "X123",
                        },
                    )
                ]
            )

        agent = _build_agent()
        with agent.override(model=FunctionModel(respond)):
            await agent.run("some id document text")

        assert seen == [[]]

    async def test_recovers_after_two_prose_answers(self) -> None:
        answers: list[str] = []

        def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            if len(answers) < 2:
                answers.append("prose")
                return ModelResponse(parts=[TextPart(content="Account holder Jane Doe.")])
            tool_name = _tool_named(info, "final_result_ExtractedProofOfAddressFields")
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name=tool_name,
                        args={"account_holder": "Jane Doe", "address": "1 Main St"},
                    )
                ]
            )

        agent = _build_agent()
        with agent.override(model=FunctionModel(respond)):
            result = await agent.run("some proof of address text")

        assert result.output == ExtractedProofOfAddressFields(
            account_holder="Jane Doe", address="1 Main St"
        )
