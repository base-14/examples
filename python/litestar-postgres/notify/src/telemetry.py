"""Custom Counter — notifications received from the articles service.

Mirrors the `articles.created` counter on the producer side so a learner can
divide them in Scout to detect drops (`notifications.received / articles.created`).
See `app/src/telemetry.py` for why import-time instrument creation is safe.
"""

from opentelemetry import metrics

_meter = metrics.get_meter("litestar-postgres-notify")

notifications_received = _meter.create_counter(
    name="notifications.received",
    description="Number of article-creation notifications received",
    unit="1",
)
