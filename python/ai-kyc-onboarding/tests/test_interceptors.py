from datetime import timedelta

from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from temporalio import activity, workflow
from temporalio.contrib.opentelemetry import OpenTelemetryPlugin
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from kyc_onboarding.interceptors import ACTIVITY_ATTEMPT_ATTRIBUTE, ActivityAttemptInterceptor
from tests._telemetry_support import global_tracer_provider


TASK_QUEUE = "attempt-probe"


@activity.defn
async def ping() -> str:
    return "pong"


@workflow.defn(name="AttemptProbeWorkflow")
class AttemptProbeWorkflow:
    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(ping, start_to_close_timeout=timedelta(seconds=5))


async def test_activity_attempt_attribute_lands_on_run_activity_span_only() -> None:
    exporter = InMemorySpanExporter()
    global_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))

    async with (
        await WorkflowEnvironment.start_time_skipping(
            plugins=[OpenTelemetryPlugin(add_temporal_spans=True)],
        ) as env,
        Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[AttemptProbeWorkflow],
            activities=[ping],
            interceptors=[ActivityAttemptInterceptor()],
        ),
    ):
        await env.client.execute_workflow(
            AttemptProbeWorkflow.run,
            id="attempt-probe-1",
            task_queue=TASK_QUEUE,
        )

    spans = exporter.get_finished_spans()
    run_activity_spans = [s for s in spans if s.name.startswith("RunActivity:")]
    assert len(run_activity_spans) == 1

    run_activity_span = run_activity_spans[0]
    assert run_activity_span.attributes is not None
    assert run_activity_span.attributes[ACTIVITY_ATTEMPT_ATTRIBUTE] == 1

    other_spans = [s for s in spans if s is not run_activity_span]
    assert other_spans, "expected sibling and parent spans to compare against"
    for span in other_spans:
        assert ACTIVITY_ATTEMPT_ATTRIBUTE not in (span.attributes or {}), span.name
