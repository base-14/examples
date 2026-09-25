import asyncio
import logging
from typing import Any

from pydantic_ai.durable_exec.temporal import AgentPlugin
from temporalio.client import Client
from temporalio.worker import Worker

from kyc_onboarding.agents import (
    FaultRegistry,
    PostgresFaultRegistry,
    StaticFaultRegistry,
    build_assessment_agent,
    build_extraction_agent,
    load_prompt,
)
from kyc_onboarding.case_agents import CaseAgents, install_case_agents
from kyc_onboarding.config import Settings, get_settings
from kyc_onboarding.interceptors import ActivityAttemptInterceptor
from kyc_onboarding.telemetry import configure_telemetry, create_temporal_client
from kyc_onboarding.workflows import KycOnboardingWorkflow


logging.basicConfig()
logger = logging.getLogger(__name__)

FALLBACK_SERVICE_NAME = "ai-kyc-onboarding-worker"


def build_case_agents(settings: Settings) -> CaseAgents:
    faults: FaultRegistry = (
        PostgresFaultRegistry(settings.kyc_db_dsn)
        if settings.faults_enabled
        else StaticFaultRegistry()
    )
    extraction_prompt = load_prompt(f"extraction_{settings.extraction_prompt_version}")
    assessment_prompt = load_prompt(f"assessment_{settings.assessment_prompt_version}")
    return CaseAgents(
        extraction=build_extraction_agent(
            instructions=extraction_prompt.system,
            base_url=settings.ollama_base_url,
            model_name=settings.extraction_model,
            faults=faults,
        ),
        assessment=build_assessment_agent(
            instructions=assessment_prompt.system,
            base_url=settings.ollama_base_url,
            model_name=settings.assessment_model,
            faults=faults,
        ),
        extraction_prompt=extraction_prompt,
        assessment_prompt=assessment_prompt,
        extraction_prompt_version=settings.extraction_prompt_version,
        assessment_prompt_version=settings.assessment_prompt_version,
        sanctions_dsn=settings.kyc_db_dsn,
    )


def create_worker(client: Client, task_queue: str, agents: CaseAgents, **options: Any) -> Worker:
    """Install the case agents and build the worker with their activities."""
    install_case_agents(agents)
    return Worker(
        client,
        task_queue=task_queue,
        workflows=[KycOnboardingWorkflow],
        plugins=[AgentPlugin(agents.extraction), AgentPlugin(agents.assessment)],
        interceptors=[ActivityAttemptInterceptor()],
        **options,
    )


async def main() -> None:
    settings = get_settings()
    configure_telemetry(FALLBACK_SERVICE_NAME)
    client = await create_temporal_client(settings)
    worker = create_worker(client, settings.temporal_task_queue, build_case_agents(settings))
    logger.info(
        "worker polling task_queue=%s address=%s faults_enabled=%s",
        settings.temporal_task_queue,
        settings.temporal_address,
        settings.faults_enabled,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
