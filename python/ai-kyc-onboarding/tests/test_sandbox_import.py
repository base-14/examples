"""Checks that a workflow module can import `kyc_onboarding.agents` inside the sandbox."""

from pydantic_ai.durable_exec.temporal import (
    _workflow_runner,  # pyright: ignore[reportPrivateUsage]
)
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner
from temporalio.workflow._definition import _Definition  # pyright: ignore[reportPrivateUsage]

from tests import _sandbox_probe_workflow


async def test_agents_module_imports_under_the_temporal_sandbox() -> None:
    # Matches the passthrough restrictions `PydanticAIPlugin` applies to a real worker.
    restrictions = _workflow_runner(SandboxedWorkflowRunner()).restrictions
    runner = SandboxedWorkflowRunner(restrictions=restrictions)

    definition = _Definition.must_from_class(_sandbox_probe_workflow.ProbeWorkflow)

    runner.prepare_workflow(definition)
