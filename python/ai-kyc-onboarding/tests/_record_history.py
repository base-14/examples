"""Records the workflow history that `test_workflow_replay` replays.

Run `uv run python -m tests._record_history` after changing the workflow's commands, then
commit the rewritten file.
"""

import asyncio
from pathlib import Path
from unittest.mock import patch

from kyc_onboarding.models import (
    ApproveDecision,
    CaseStatus,
    DocumentType,
    EscalateDecision,
    RequestResubmissionDecision,
    ReviewDecision,
    RiskLevel,
)
from kyc_onboarding.tools import SanctionsScreeningResult
from kyc_onboarding.worker import create_worker
from kyc_onboarding.workflows import KycOnboardingWorkflow
from tests._workflow_support import (
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    case_input,
    document,
    required_documents,
    send_documents,
    start_case,
    time_skipping_env,
    wait_for_status,
)


HISTORY_PATH = Path(__file__).parent / "histories" / "resubmission_escalation_review.json"
TASK_QUEUE = "kyc-record-history"

DECISIONS = [
    RequestResubmissionDecision(
        reasons=["address on id does not match proof_of_address"],
        documents_to_resend=[DocumentType.proof_of_address],
    ),
    EscalateDecision(risk_level=RiskLevel.medium, reasons=["partial sanctions match"]),
    ApproveDecision(),
]


def _clear(name: str, dsn: str) -> SanctionsScreeningResult:
    return SanctionsScreeningResult(result="clear", matched_entry=None, score=None)


async def record() -> str:
    agents = build_test_agents(ScriptedExtraction(), ScriptedAssessment(decisions=DECISIONS))
    with patch("kyc_onboarding.agents.tools._screen_sanctions", _clear):
        async with time_skipping_env() as env, create_worker(env.client, TASK_QUEUE, agents):
            handle = await start_case(env.client, TASK_QUEUE, case_input("case-recorded"))
            await send_documents(handle, required_documents())
            await wait_for_status(handle, CaseStatus.awaiting_documents, resubmission_round=1)
            await send_documents(handle, [document(DocumentType.proof_of_address)])
            await wait_for_status(handle, CaseStatus.awaiting_review, resubmission_round=1)
            await handle.execute_update(
                KycOnboardingWorkflow.submit_review,
                ReviewDecision(decision="approve", reviewer="r.okafor"),
            )
            await handle.result()
            history = await handle.fetch_history()
    return history.to_json()


if __name__ == "__main__":
    HISTORY_PATH.write_text(asyncio.run(record()))
    print(f"wrote {HISTORY_PATH}")
