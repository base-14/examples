from scripts.collector_debug import Telemetry, parse


SAMPLE = """\
2026-09-24T13:42:15.100Z\tinfo\tTraces\t{"resource spans": 2, "spans": 2}
2026-09-24T13:42:15.100Z\tinfo\tResourceSpans #0
Resource SchemaURL: \nResource attributes:
     -> service.instance.id: Str(api-1)
     -> service.name: Str(ai-kyc-onboarding-api)
ScopeSpans #0
InstrumentationScope opentelemetry.instrumentation.fastapi 0.65b0
Span #0
    Trace ID       : aaaa
    Parent ID      : \n    ID             : a1
    Name           : POST /cases
    Kind           : Server
    Status code    : Unset
    Status message : \nAttributes:
     -> http.status_code: Int(201)
ResourceSpans #1
Resource SchemaURL: \nResource attributes:
     -> service.instance.id: Str(worker-1)
     -> service.name: Str(ai-kyc-onboarding-worker)
ScopeSpans #0
InstrumentationScope temporalio
Span #0
    Trace ID       : aaaa
    Parent ID      : b0
    ID             : b1
    Name           : RunActivity:agent__kyc-extraction__model_request
    Kind           : Server
    Status code    : Error
    Status message : ollama unreachable
Attributes:
     -> temporalActivityID: Str(1)
     -> base14.temporal.activity.attempt: Int(2)
Events:
SpanEvent #0
     -> Name: exception
     -> Attributes::
          -> exception.stacktrace: Str(Traceback (most recent call last):
  File "faults.py", line 235, in request
ConnectionError: ollama unreachable (attempt 2)
)
          -> exception.escaped: Str(False)
Span #1
    Trace ID       : aaaa
    Parent ID      : b0
    ID             : b2
    Name           : kyc.document_received
    Status code    : Unset
Attributes:
     -> base14.kyc.document_type: Str(id)
Links:
SpanLink #0
     -> Trace ID: cccc
     -> ID: c1
     -> TraceState: \n     -> DroppedAttributesCount: 0
2026-09-24T13:42:15.395Z\tinfo\tResourceLog #0
Resource attributes:
     -> service.instance.id: Str(worker-1)
     -> service.name: Str(ai-kyc-onboarding-worker)
ScopeLogs #0
InstrumentationScope temporalio.activity
LogRecord #0
SeverityText: ERROR
SeverityNumber: Error(17)
Body: Str(injected model_unavailable fault)
Attributes:
     -> base14.kyc.case_id: Str(case-1)
     -> exception.stacktrace: Str(Traceback (most recent call last):
Trace ID: aaaa
Span ID: b1
Flags: 1
2026-09-24T13:42:16.000Z\tinfo\tResourceMetrics #0
Resource attributes:
     -> service.name: Str(ai-kyc-onboarding-worker)
ScopeMetrics #0
InstrumentationScope kyc_onboarding.case_metrics
Metric #0
Descriptor:
     -> Name: base14.kyc.cases
     -> DataType: Sum
NumberDataPoints #0
Data point attributes:
     -> base14.kyc.outcome: Str(approved)
StartTimestamp: 2026-09-24 13:25:55 +0000 UTC
Value: 2
Metric #1
Descriptor:
     -> Name: base14.kyc.review.wait
     -> DataType: Histogram
HistogramDataPoints #0
Data point attributes:
     -> base14.kyc.review_decision: Str(reject)
Count: 1
2026-09-24T13:42:17.000Z\twarn\tinternal/retry_sender.go:133\tExporting failed. Will retry\t{"otelcol.component.id": "otlp_http/b14"}
"""


def _telemetry() -> Telemetry:
    return parse(SAMPLE.splitlines())


class TestSpans:
    def test_reads_ids_names_and_status(self) -> None:
        spans = _telemetry().spans

        assert [(s.trace_id, s.parent_id, s.span_id, s.name, s.status) for s in spans] == [
            ("aaaa", "", "a1", "POST /cases", "Unset"),
            ("aaaa", "b0", "b1", "RunActivity:agent__kyc-extraction__model_request", "Error"),
            ("aaaa", "b0", "b2", "kyc.document_received", "Unset"),
        ]

    def test_each_span_carries_its_own_resource(self) -> None:
        spans = _telemetry().spans

        assert [(s.resource.service, s.resource.instance) for s in spans] == [
            ("ai-kyc-onboarding-api", "api-1"),
            ("ai-kyc-onboarding-worker", "worker-1"),
            ("ai-kyc-onboarding-worker", "worker-1"),
        ]

    def test_reads_typed_attributes_and_skips_event_attributes(self) -> None:
        activity = _telemetry().spans[1]

        assert activity.attributes == {
            "temporalActivityID": "1",
            "base14.temporal.activity.attempt": 2,
        }

    def test_reads_links(self) -> None:
        (link,) = _telemetry().spans[2].links

        assert (link.trace_id, link.span_id) == ("cccc", "c1")


class TestLogs:
    def test_reads_severity_body_and_span_context(self) -> None:
        (log,) = _telemetry().logs

        assert (log.severity, log.body, log.trace_id, log.span_id) == (
            "ERROR",
            "injected model_unavailable fault",
            "aaaa",
            "b1",
        )
        assert log.attributes["base14.kyc.case_id"] == "case-1"
        assert log.resource.instance == "worker-1"


class TestMetrics:
    def test_reads_data_points_with_their_metric_and_attributes(self) -> None:
        points = _telemetry().data_points

        assert [(p.metric, p.attributes) for p in points] == [
            ("base14.kyc.cases", {"base14.kyc.outcome": "approved"}),
            ("base14.kyc.review.wait", {"base14.kyc.review_decision": "reject"}),
        ]


class TestCollectorLines:
    def test_keeps_the_collector_warnings_only(self) -> None:
        (warning,) = _telemetry().collector_warnings

        assert "Exporting failed" in warning
