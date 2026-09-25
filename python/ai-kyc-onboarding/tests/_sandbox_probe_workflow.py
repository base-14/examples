"""A probe workflow that imports `kyc_onboarding.agents` at module load.

`test_sandbox_import` prepares it under the worker's sandbox restrictions.
"""

from temporalio import workflow

from kyc_onboarding.agents import build_assessment_agent, build_extraction_agent


_ = (build_assessment_agent, build_extraction_agent)


@workflow.defn(name="SandboxImportProbeWorkflow")
class ProbeWorkflow:
    @workflow.run
    async def run(self) -> None:
        return None
