#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "claude-agent-sdk==0.2.163",
#   "opentelemetry-sdk==1.45.0",
#   "opentelemetry-exporter-otlp-proto-http==1.45.0",
# ]
# ///
"""Runs one Claude Agent SDK query under a parent span.

The SDK starts the Claude Code CLI as a child process. The CLI reads the telemetry
variables from this process's environment and joins this trace through TRACEPARENT.
Prints one JSON line with the trace id for scripts/drive.sh.
"""

import asyncio
import json
import os

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.propagate import inject
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

PROMPT = "Read notes.txt with the Read tool and summarise it in one sentence."


async def run_query(traceparent: str) -> ResultMessage | None:
    options = ClaudeAgentOptions(
        model=os.environ["CLAUDE_RIG_MODEL"],
        cwd=os.environ["CLAUDE_RIG_WORKSPACE"],
        tools=["Read"],
        allowed_tools=["Read"],
        max_turns=4,
        max_budget_usd=float(os.environ["CLAUDE_RIG_TURN_BUDGET_USD"]),
        env={"TRACEPARENT": traceparent},
        extra_args={"bare": None},
    )
    result = None
    async for message in query(prompt=PROMPT, options=options):
        if isinstance(message, ResultMessage):
            result = message
    return result


def main() -> None:
    provider = TracerProvider(
        resource=Resource.create({"service.name": "agent-sdk-host"})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    tracer = provider.get_tracer("claude-code-telemetry-rig")

    with tracer.start_as_current_span("summarise_notes") as span:
        carrier: dict[str, str] = {}
        inject(carrier)
        result = asyncio.run(run_query(carrier["traceparent"]))
        trace_id = format(span.get_span_context().trace_id, "032x")

    provider.shutdown()
    print(
        json.dumps(
            {
                "trace_id": trace_id,
                "session_id": result.session_id if result else None,
                "is_error": result.is_error if result else True,
            }
        )
    )


if __name__ == "__main__":
    main()
