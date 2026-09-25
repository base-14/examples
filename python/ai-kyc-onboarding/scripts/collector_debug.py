"""Parse the collector's detailed debug exporter output into spans, logs and data points.

Keeps only the fields the verification needs, and the first line of multi-line values.
"""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Literal


Attributes = dict[str, str | int]


@dataclass
class Resource:
    attributes: Attributes = field(default_factory=dict)

    @property
    def service(self) -> str:
        return str(self.attributes.get("service.name", ""))

    @property
    def instance(self) -> str:
        return str(self.attributes.get("service.instance.id", ""))


@dataclass
class Link:
    trace_id: str = ""
    span_id: str = ""


@dataclass
class Span:
    resource: Resource
    trace_id: str = ""
    parent_id: str = ""
    span_id: str = ""
    name: str = ""
    status: str = ""
    attributes: Attributes = field(default_factory=dict)
    links: list[Link] = field(default_factory=list)


@dataclass
class LogRecord:
    resource: Resource
    severity: str = ""
    body: str = ""
    trace_id: str = ""
    span_id: str = ""
    attributes: Attributes = field(default_factory=dict)


@dataclass
class DataPoint:
    metric: str
    attributes: Attributes = field(default_factory=dict)


@dataclass
class Telemetry:
    spans: list[Span] = field(default_factory=list)
    logs: list[LogRecord] = field(default_factory=list)
    data_points: list[DataPoint] = field(default_factory=list)
    collector_warnings: list[str] = field(default_factory=list)


Section = Literal["other", "resource", "attributes", "links", "descriptor", "point"]

_RESOURCE_START = re.compile(r"(^|\t)(ResourceSpans|ResourceLog|ResourceMetrics) #\d+$")
_COLLECTOR_LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T\S+\t(\w+)\t")
_SPAN_FIELD = re.compile(r"^    (Trace ID|Parent ID|ID|Name|Status code)\s*: ?(.*)$")
_LOG_FIELD = re.compile(r"^(SeverityText|Body|Trace ID|Span ID): (.*)$")
_LINK_FIELD = re.compile(r"^\s+-> (Trace ID|ID): (\S*)$")
_DESCRIPTOR_NAME = re.compile(r"^\s+-> Name: (\S+)$")
_ATTRIBUTE = re.compile(r"^\s+-> ([^:]+): (\w+)\((.*)$")
_TYPED_VALUE = re.compile(r"^(\w+)\((.*)$")

_SPAN_FIELD_NAMES = {
    "Trace ID": "trace_id",
    "Parent ID": "parent_id",
    "ID": "span_id",
    "Name": "name",
    "Status code": "status",
}
_LOG_FIELD_NAMES = {
    "SeverityText": "severity",
    "Body": "body",
    "Trace ID": "trace_id",
    "Span ID": "span_id",
}


def typed_value(kind: str, raw: str) -> str | int:
    value = raw.removesuffix(")")
    if kind == "Int":
        try:
            return int(value)
        except ValueError:
            return value
    return value


class _DebugOutputParser:
    def __init__(self) -> None:
        self.telemetry = Telemetry()
        self._resource = Resource()
        self._section: Section = "other"
        self._span: Span | None = None
        self._log: LogRecord | None = None
        self._metric = ""
        self._point: DataPoint | None = None
        self._markers: list[tuple[re.Pattern[str], Callable[[], None]]] = [
            (re.compile(r"^Resource attributes:$"), self._start_resource_attributes),
            (re.compile(r"^InstrumentationScope "), self._start_scope),
            (re.compile(r"^Span #\d+$"), self._start_span),
            (re.compile(r"^LogRecord #\d+$"), self._start_log),
            (re.compile(r"^Metric #\d+$"), self._start_metric),
            (re.compile(r"^Descriptor:$"), self._start_descriptor),
            (re.compile(r"^(Number|Histogram)DataPoints #\d+$"), self._start_point),
            (re.compile(r"^Data point attributes:$"), self._start_point_attributes),
            (re.compile(r"^Attributes:$"), self._start_attributes),
            (re.compile(r"^Links:$"), self._start_links),
            (re.compile(r"^SpanLink #\d+$"), self._start_link),
            (re.compile(r"^(Events:|SpanEvent #\d+)$"), self._start_other),
            (re.compile(r"^(StartTimestamp|Timestamp|Value|Count|Sum|Min|Max)"), self._end_point),
        ]

    def feed(self, line: str) -> None:
        if _RESOURCE_START.search(line):
            self._start_resource()
            return
        if collector_line := _COLLECTOR_LINE.match(line):
            if collector_line.group(1) in ("warn", "error"):
                self.telemetry.collector_warnings.append(line)
            return
        for pattern, start in self._markers:
            if pattern.match(line):
                start()
                return
        self._read_field(line)

    def _read_field(self, line: str) -> None:
        if self._span is not None and (span_field := _SPAN_FIELD.match(line)):
            key, value = span_field.groups()
            setattr(self._span, _SPAN_FIELD_NAMES[key], value)
        elif self._log is not None and (log_field := _LOG_FIELD.match(line)):
            key, value = log_field.groups()
            if key == "Body" and (typed := _TYPED_VALUE.match(value)):
                value = str(typed_value(*typed.groups()))
            setattr(self._log, _LOG_FIELD_NAMES[key], value)
        elif self._section == "links" and (link_field := _LINK_FIELD.match(line)):
            key, value = link_field.groups()
            if self._span is not None and self._span.links:
                setattr(self._span.links[-1], "trace_id" if key == "Trace ID" else "span_id", value)
        elif self._section == "descriptor" and (name := _DESCRIPTOR_NAME.match(line)):
            self._metric = name.group(1)
        elif (attribute := _ATTRIBUTE.match(line)) and (target := self._attributes()) is not None:
            key, kind, raw = attribute.groups()
            target.setdefault(key, typed_value(kind, raw))

    def _attributes(self) -> Attributes | None:
        if self._section == "resource":
            return self._resource.attributes
        if self._section == "point" and self._point is not None:
            return self._point.attributes
        if self._section == "attributes":
            item = self._log or self._span
            return item.attributes if item is not None else None
        return None

    def _start_resource(self) -> None:
        self._resource = Resource()
        self._span, self._log, self._point, self._metric = None, None, None, ""
        self._section = "other"

    def _start_resource_attributes(self) -> None:
        self._section = "resource"

    def _start_scope(self) -> None:
        self._span, self._log, self._point = None, None, None
        self._section = "other"

    def _start_span(self) -> None:
        self._span, self._log = Span(resource=self._resource), None
        self.telemetry.spans.append(self._span)
        self._section = "other"

    def _start_log(self) -> None:
        self._log, self._span = LogRecord(resource=self._resource), None
        self.telemetry.logs.append(self._log)
        self._section = "other"

    def _start_metric(self) -> None:
        self._metric, self._point = "", None
        self._section = "other"

    def _start_descriptor(self) -> None:
        self._section = "descriptor"

    def _start_point(self) -> None:
        self._point = DataPoint(metric=self._metric)
        self.telemetry.data_points.append(self._point)
        self._section = "other"

    def _start_point_attributes(self) -> None:
        self._section = "point"

    def _end_point(self) -> None:
        if self._section in ("point", "descriptor"):
            self._section = "other"

    def _start_attributes(self) -> None:
        self._section = "attributes"

    def _start_links(self) -> None:
        self._section = "links"

    def _start_link(self) -> None:
        self._section = "links"
        if self._span is not None:
            self._span.links.append(Link())

    def _start_other(self) -> None:
        self._section = "other"


def parse(lines: Iterable[str]) -> Telemetry:
    parser = _DebugOutputParser()
    for line in lines:
        parser.feed(line.rstrip("\n"))
    return parser.telemetry
