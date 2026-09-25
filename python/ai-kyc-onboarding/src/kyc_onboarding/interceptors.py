"""Worker interceptor that records the activity attempt number on its `RunActivity` span.

It goes in `Worker(interceptors=...)`, not the client plugins. Client interceptors run
first, so `OpenTelemetryPlugin` has opened the span by the time this one sets the attribute.
"""

from __future__ import annotations

from typing import Any

from opentelemetry import trace
from temporalio import activity
from temporalio.worker import ActivityInboundInterceptor, ExecuteActivityInput, Interceptor

from kyc_onboarding.attributes import ACTIVITY_ATTEMPT_ATTRIBUTE


__all__ = ["ACTIVITY_ATTEMPT_ATTRIBUTE", "ActivityAttemptInterceptor"]


class ActivityAttemptInterceptor(Interceptor):
    def intercept_activity(self, next: ActivityInboundInterceptor) -> ActivityInboundInterceptor:
        return _ActivityAttemptInboundInterceptor(next)


class _ActivityAttemptInboundInterceptor(ActivityInboundInterceptor):
    async def execute_activity(self, input: ExecuteActivityInput) -> Any:
        trace.get_current_span().set_attribute(ACTIVITY_ATTEMPT_ATTRIBUTE, activity.info().attempt)
        return await self.next.execute_activity(input)
