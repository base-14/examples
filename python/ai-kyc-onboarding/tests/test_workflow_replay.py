from temporalio.client import WorkflowHistory
from temporalio.worker import Replayer

from kyc_onboarding.case_agents import install_case_agents
from kyc_onboarding.workflows import KycOnboardingWorkflow
from tests._record_history import HISTORY_PATH
from tests._telemetry_support import global_tracer_provider
from tests._workflow_support import (
    ScriptedAssessment,
    ScriptedExtraction,
    build_test_agents,
    client_plugins,
)


async def test_recorded_case_history_replays_without_nondeterminism() -> None:
    global_tracer_provider()
    install_case_agents(build_test_agents(ScriptedExtraction(), ScriptedAssessment()))
    history = WorkflowHistory.from_json("case-recorded", HISTORY_PATH.read_text())

    result = await Replayer(
        workflows=[KycOnboardingWorkflow], plugins=client_plugins()
    ).replay_workflow(history)

    assert result.replay_failure is None
