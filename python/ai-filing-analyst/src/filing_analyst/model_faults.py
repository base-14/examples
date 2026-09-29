"""Model failures injected on demand, behind `FILING_FAULTS_ENABLED`.

The Strands adapter injects them in a wrapper around the analyst's model. The other adapters
inject `model_unavailable` and `slow_model` in their before-model hook, and rewrite the final
answer for `bad_output` and `ungrounded_answer`.
"""

import asyncio
from enum import StrEnum
from typing import Any


INVENTED_ACCESSION = "0000000000-00-000000"
INVALID_ACCESSION = "not-an-accession"
SLOW_MODEL_SECONDS = 60.0
SLOW_MODEL_POLL_SECONDS = 0.05


class ModelFault(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    SLOW_MODEL = "slow_model"
    BAD_OUTPUT = "bad_output"
    UNGROUNDED_ANSWER = "ungrounded_answer"


def invalid_answer(answer: dict[str, Any]) -> dict[str, Any]:
    figures = answer.get("figures") or [{}]
    return {**answer, "figures": [{**figures[0], "accession": INVALID_ACCESSION}]}


def ungrounded_answer(answer: dict[str, Any]) -> dict[str, Any]:
    figures = answer.get("figures") or [
        {"concept": "revenue", "value": 1.0, "unit": "USD", "fiscal_year": 2024, "form": "10-K"}
    ]
    return {**answer, "figures": [{**f, "accession": INVENTED_ACCESSION} for f in figures]}


async def before_model_call(fault: ModelFault | None, slow_seconds: float) -> None:
    if fault == ModelFault.MODEL_UNAVAILABLE:
        raise ConnectionError("Failed to connect to Ollama (injected model_unavailable)")
    if fault == ModelFault.SLOW_MODEL:
        await asyncio.sleep(slow_seconds)


def faulted_answer(fault: ModelFault | None, answer: dict[str, Any]) -> dict[str, Any]:
    if fault == ModelFault.BAD_OUTPUT:
        return invalid_answer(answer)
    if fault == ModelFault.UNGROUNDED_ANSWER:
        return ungrounded_answer(answer)
    return answer
