"""Print a case's Temporal activities as JSON for scripts/test-api.sh.

Run it in the api container: `python - history|pending <case_id> < scripts/case_activities.py`.
"""

import asyncio
import json
import os
import sys
from typing import Any

from google.protobuf.timestamp_pb2 import Timestamp
from temporalio.api.enums.v1 import PendingActivityState
from temporalio.client import Client


def _decode(payloads: Any) -> list[Any]:
    decoded = []
    for payload in payloads:
        try:
            decoded.append(json.loads(payload.data))
        except ValueError:
            decoded.append(None)
    return decoded


def _unix_time(timestamp: Timestamp) -> float:
    return timestamp.seconds + timestamp.nanos / 1e9


def _has_retry_prompt(request: Any) -> bool:
    messages = request.get("messages", []) if isinstance(request, dict) else []
    return any(
        part.get("part_kind") == "retry-prompt"
        for message in messages
        for part in message.get("parts", [])
    )


def _describe_activity(activity_type: str, first_input: Any) -> dict[str, Any]:
    parts = activity_type.split("__")
    agent = parts[1] if len(parts) > 1 else None
    if activity_type.endswith("__model_request"):
        return {
            "agent": agent,
            "kind": "model_request",
            "tool": None,
            "has_retry_prompt": _has_retry_prompt(first_input),
        }
    if activity_type.endswith("__call_tool"):
        tool = first_input.get("name") if isinstance(first_input, dict) else None
        return {"agent": agent, "kind": "call_tool", "tool": tool, "has_retry_prompt": False}
    return {"agent": agent, "kind": activity_type, "tool": None, "has_retry_prompt": False}


async def history(client: Client, case_id: str) -> list[dict[str, Any]]:
    activities: dict[int, dict[str, Any]] = {}
    events = (await client.get_workflow_handle(case_id).fetch_history()).events
    for event in events:
        kind = event.WhichOneof("attributes")
        if kind is None:
            continue
        attributes = getattr(event, kind)
        if kind == "activity_task_scheduled_event_attributes":
            first_input = next(iter(_decode(attributes.input.payloads)), None)
            activities[event.event_id] = {
                "activity_id": attributes.activity_id,
                "activity_type": attributes.activity_type.name,
                **_describe_activity(attributes.activity_type.name, first_input),
                "attempt": None,
                "last_failure": None,
                "outcome": "scheduled",
                "closed_at": None,
            }
        elif kind == "activity_task_started_event_attributes":
            activity = activities[attributes.scheduled_event_id]
            activity["attempt"] = attributes.attempt
            activity["last_failure"] = attributes.last_failure.message or None
        elif kind in (
            "activity_task_completed_event_attributes",
            "activity_task_failed_event_attributes",
            "activity_task_timed_out_event_attributes",
            "activity_task_canceled_event_attributes",
        ):
            outcome = kind.removeprefix("activity_task_").removesuffix("_event_attributes")
            activity = activities[attributes.scheduled_event_id]
            activity["outcome"] = outcome
            activity["closed_at"] = _unix_time(event.event_time)
    return list(activities.values())


async def pending(client: Client, case_id: str) -> list[dict[str, Any]]:
    description = await client.get_workflow_handle(case_id).describe()
    return [
        {
            "activity_id": activity.activity_id,
            "activity_type": activity.activity_type.name,
            "attempt": activity.attempt,
            "state": PendingActivityState.Name(activity.state),
        }
        for activity in description.raw_description.pending_activities
    ]


async def main(mode: str, case_id: str) -> None:
    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "temporal:7233"))
    result = await (history if mode == "history" else pending)(client, case_id)
    print(json.dumps(result))


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("history", "pending"):
        sys.exit("usage: case_activities.py history|pending <case_id>")
    asyncio.run(main(sys.argv[1], sys.argv[2]))
