"""Check each question's trace, logs and metrics in the collector's debug output.

Reads `.harness/last-run.json` from `scripts/test-api.sh` and the collector output for that run.
Prints one PASS or FAIL line per check, the span count per question, and exits 1 on any FAIL.

Usage: python -m scripts.verify_questions [--allow-partial] RUN_FILE COLLECTOR_LOG [SELF_METRICS]
"""

import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.collector_debug import LogRecord, Span, Telemetry, parse


SERVER_SPAN = "POST /questions"
ANALYST_SPAN = "invoke_agent analyst"
RANKING_SPAN = "invoke_agent ranking"
VERIFY_SPAN = "filing.verify_answer"
QUESTION_ID = "base14.filing.question_id"
ENDPOINT = "base14.sec.endpoint"
ERROR = "Error"
HTTP_OK = 200
SCOUT_EXPORTER = "otlp_http/b14"
SIGNALS = ("spans", "log_records", "metric_points")
OUTCOME = "base14.filing.outcome"
QUESTION_ATTRIBUTES = (
    QUESTION_ID,
    "base14.filing.ticker",
    "base14.filing.cik",
    "base14.filing.fixture_date",
)
AGENT_ATTRIBUTES = ("base14.prompt.version", "base14.gen_ai.model.digest")
CHAT_ATTRIBUTES = (
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "base14.gen_ai.cost",
    "base14.gen_ai.cost.simulated",
)
APPLICATION_METRICS = (
    "base14.filing.questions",
    "base14.filing.question.duration",
    "base14.filing.sec.requests",
    "base14.filing.facts.loaded",
    "base14.filing.rankings",
)
GEN_AI_CLIENT_METRICS = ("gen_ai.client.operation.duration", "gen_ai.client.token.usage")
# Ollama reports no prompt cache usage, so Strands records no cache token metrics.
STRANDS_METRICS = (
    "strands.event_loop.cycle_count",
    "strands.event_loop.start_cycle",
    "strands.event_loop.end_cycle",
    "strands.event_loop.cycle_duration",
    "strands.event_loop.latency",
    "strands.event_loop.input.tokens",
    "strands.event_loop.output.tokens",
    "strands.model.time_to_first_token",
    "strands.tool.call_count",
    "strands.tool.success_count",
    "strands.tool.error_count",
    "strands.tool.duration",
)


@dataclass(frozen=True)
class Profile:
    """What one framework emits. `question_spans` carry the question's attributes;
    `agent_spans` also carry the agent's prompt version, model digest, provider and server.
    `wrapper` is the span a framework puts between the server span and the analyst's
    `invoke_agent`, if any. `conversation` is where the conversation ID is the question ID:
    every question span, the analyst's spans only, or nowhere. `model_failure_span` is the span
    that fails when the model is unreachable, if the framework opens one. The analyst may run
    twice for one question, when a run that ends in text gets a reminder to call the answer
    tool."""

    question_spans: tuple[str, ...]
    agent_spans: tuple[str, ...]
    model_span: str
    metrics: tuple[str, ...]
    wrapper: str | None = None
    conversation: str | None = "all"
    tool_status: bool = False
    answer_tool_span: str | None = None
    model_failure_span: str | None = "chat"
    server_on_model_spans: bool = True


PROFILES = {
    "strands": Profile(
        question_spans=("invoke_agent", "execute_event_loop_cycle", "chat", "execute_tool"),
        agent_spans=("invoke_agent", "execute_event_loop_cycle", "chat", "execute_tool"),
        model_span="chat",
        metrics=STRANDS_METRICS,
        tool_status=True,
        answer_tool_span="execute_tool FilingAnswer",
    ),
    "adk": Profile(
        question_spans=(
            "invocation",
            "invoke_agent",
            "call_llm",
            "generate_content",
            "execute_tool",
        ),
        agent_spans=("invoke_agent", "generate_content"),
        model_span="generate_content",
        metrics=(
            *GEN_AI_CLIENT_METRICS,
            "gen_ai.execute_tool.duration",
            "gen_ai.invoke_agent.duration",
            "gen_ai.invoke_agent.inference_calls",
            "gen_ai.invoke_agent.tool_calls",
        ),
        wrapper="invocation",
        conversation="analyst",
        model_failure_span="call_llm",
    ),
    "maf": Profile(
        question_spans=("invoke_agent", "chat", "execute_tool"),
        agent_spans=("invoke_agent", "chat"),
        model_span="chat",
        metrics=(*GEN_AI_CLIENT_METRICS, "agent_framework.function.invocation.duration"),
        conversation=None,
        model_failure_span=None,
        server_on_model_spans=False,
    ),
    "openai-agents": Profile(
        question_spans=("invoke_workflow", "invoke_agent", "chat", "execute_tool"),
        agent_spans=("invoke_agent", "chat"),
        model_span="chat",
        metrics=(
            *GEN_AI_CLIENT_METRICS,
            "gen_ai.execute_tool.duration",
            "gen_ai.invoke_agent.duration",
            "gen_ai.invoke_workflow.duration",
        ),
        wrapper="invoke_workflow",
        conversation=None,
        model_failure_span=None,
    ),
}


@dataclass
class Report:
    failures: int = 0
    lines: list[str] = field(default_factory=list)

    def check(self, label: str, passed: bool, detail: str = "") -> None:
        if passed:
            print(f"  PASS {label}")
        else:
            self.failures += 1
            print(f"  FAIL {label}" + (f": {detail}" if detail else ""))


class Trace:
    def __init__(self, spans: list[Span], logs: list[LogRecord]) -> None:
        self.spans = spans
        self.logs = logs
        self._by_id = {span.span_id: span for span in spans}

    def named(self, name: str) -> list[Span]:
        return [span for span in self.spans if span.name == name]

    def one(self, name: str) -> Span | None:
        found = self.named(name)
        return found[0] if len(found) == 1 else None

    def parent(self, span: Span) -> Span | None:
        return self._by_id.get(span.parent_id)

    def under(self, ancestor: Span) -> list[Span]:
        """Every span below `ancestor`."""
        below = []
        for span in self.spans:
            current = self.parent(span)
            while current is not None:
                if current.span_id == ancestor.span_id:
                    below.append(span)
                    break
                current = self.parent(current)
        return below

    def sec_calls(self, endpoint: str) -> list[Span]:
        calls = [span for span in self.spans if span.attributes.get(ENDPOINT) == endpoint]
        return sorted(calls, key=lambda span: int(span.attributes.get("base14.sec.attempt", 0)))

    def logged(self, severity: str, text: str) -> bool:
        return any(log.severity.startswith(severity) and text in log.body for log in self.logs)


@dataclass
class Question:
    scenario: str
    question_id: str
    result: dict[str, Any]
    trace: Trace
    index: int
    profile: Profile

    @property
    def last(self) -> bool:
        return self.index == len(self.result["question_ids"]) - 1


def find_trace(telemetry: Telemetry, question_id: str) -> Trace | None:
    servers = [
        span
        for span in telemetry.spans
        if span.name == SERVER_SPAN and span.attributes.get(QUESTION_ID) == question_id
    ]
    if len(servers) != 1:
        return None
    trace_id = servers[0].trace_id
    return Trace(
        [span for span in telemetry.spans if span.trace_id == trace_id],
        [log for log in telemetry.logs if log.trace_id == trace_id],
    )


def check_common(report: Report, question: Question, outcome: str | None) -> Span:
    trace = question.trace
    server = trace.one(SERVER_SPAN)
    assert server is not None
    report.check(
        "server span outcome",
        server.attributes.get("base14.filing.outcome") == outcome,
        f"{server.attributes.get('base14.filing.outcome')} against the harness's {outcome}",
    )
    report.check(
        "server span ticker and SEC calls",
        "base14.filing.ticker" in server.attributes
        and "base14.filing.sec_calls" in server.attributes,
    )
    report.check("question received logged", trace.logged("INFO", "received for"))
    unlabelled = [log.body[:60] for log in trace.logs if QUESTION_ID not in log.attributes]
    report.check("every log record carries the question ID", not unlabelled, str(unlabelled))
    exported = {span.span_id for span in trace.spans}
    orphans = [log.body[:60] for log in trace.logs if log.span_id and log.span_id not in exported]
    report.check("every log record points at an exported span", not orphans, str(orphans))
    untyped = [
        span.name
        for span in trace.spans
        if span.status == ERROR and "error.type" not in span.attributes
    ]
    report.check("every failed span has error.type", not untyped, str(untyped))
    return server


def _starts(span: Span, prefixes: tuple[str, ...]) -> bool:
    return span.name.startswith(prefixes)


def is_model_span(span: Span, profile: Profile) -> bool:
    return span.name == profile.model_span or span.name.startswith(f"{profile.model_span} ")


def analyst_run(trace: Trace, analyst: Span) -> list[Span]:
    """The analyst's spans, without the ranking agent's."""
    ranking = trace.one(RANKING_SPAN)
    inner = {span.span_id for span in trace.under(ranking)} if ranking else set()
    if ranking is not None:
        inner.add(ranking.span_id)
    return [s for s in [analyst, *trace.under(analyst)] if s.span_id not in inner]


def check_agent_run(report: Report, question: Question, server: Span) -> Span | None:
    trace, profile = question.trace, question.profile
    analysts = trace.named(ANALYST_SPAN)

    def under_server(analyst: Span) -> bool:
        parent = trace.parent(analyst)
        return parent is not None and (
            parent.span_id == server.span_id
            or (
                parent.name.startswith(profile.wrapper or SERVER_SPAN)
                and parent.parent_id == server.span_id
            )
        )

    report.check(
        "invoke_agent analyst under the server span",
        bool(analysts) and all(under_server(analyst) for analyst in analysts),
    )
    if not analysts:
        return None
    analyst = analysts[0]
    run = [s for s in trace.under(server) if _starts(s, profile.question_spans)]
    agents = [s for s in run if _starts(s, profile.agent_spans)]
    missing = sorted(
        {
            f"{span.name}:{key}"
            for span in run
            for key in QUESTION_ATTRIBUTES
            if key not in span.attributes
        }
        | {
            f"{span.name}:{key}"
            for span in agents
            for key in AGENT_ATTRIBUTES
            if key not in span.attributes
        }
    )
    report.check("question attributes on the agent run", not missing, ", ".join(missing[:5]))
    if profile.conversation is not None:
        spans = (
            run
            if profile.conversation == "all"
            else [s for analyst in analysts for s in analyst_run(trace, analyst)]
        )
        spans = [s for s in spans if _starts(s, profile.agent_spans)]
        report.check(
            f"conversation ID is the question ID on the {profile.conversation} spans",
            all(
                span.attributes.get("gen_ai.conversation.id") == question.question_id
                for span in spans
            ),
        )
    model_spans = [span for span in run if is_model_span(span, profile)]
    report.check(
        "provider Ollama on every model span"
        + (", with its server" if profile.server_on_model_spans else ""),
        all(
            span.attributes.get("gen_ai.provider.name") == "ollama"
            and (
                not profile.server_on_model_spans
                or (span.attributes.get("server.address") and span.attributes.get("server.port"))
            )
            for span in model_spans
        ),
    )
    report.check(
        "model digests read from Ollama",
        all(
            span.attributes.get("base14.gen_ai.model.digest") not in (None, "unknown")
            for span in agents
        ),
    )
    # A model call that never reached the model has no usage to report.
    completed = [span for span in model_spans if span.status != ERROR]
    bare = [key for span in completed for key in CHAT_ATTRIBUTES if key not in span.attributes]
    report.check(
        "tokens and cost on every completed model span",
        not bare,
        str(sorted(set(bare))),
    )
    return analyst


def check_served(report: Report, question: Question, server: Span) -> None:
    trace = question.trace
    check_agent_run(report, question, server)
    verify = trace.one(VERIFY_SPAN)
    report.check(
        "filing.verify_answer under the server span with its counts",
        verify is not None
        and verify.parent_id == server.span_id
        and "base14.filing.figure_count" in verify.attributes
        and "base14.filing.citations_verified" in verify.attributes,
    )
    report.check("answer returned logged", trace.logged("INFO", "returned with"))


def check_ranking(report: Report, question: Question, server: Span) -> None:
    trace = question.trace
    tool = trace.one("execute_tool rank_among_filers")
    ranking = trace.one(RANKING_SPAN)
    report.check(
        "invoke_agent ranking under execute_tool rank_among_filers",
        tool is not None and ranking is not None and ranking in trace.under(tool),
    )
    if ranking is None:
        return
    analysts = trace.named(ANALYST_SPAN)
    report.check(
        "ranking agent carries its own digest",
        bool(analysts)
        and all(
            ranking.attributes.get("base14.gen_ai.model.digest")
            != analyst.attributes.get("base14.gen_ai.model.digest")
            for analyst in analysts
        ),
    )
    frames = [s for s in trace.under(ranking) if s.name == "execute_tool frame_values"]
    report.check("execute_tool frame_values under the ranking agent", len(frames) >= 1)
    calls = trace.sec_calls("frames")
    report.check(
        "frames client span under execute_tool frame_values",
        bool(calls) and bool(frames) and all(trace.parent(c) in frames for c in calls),
    )


def check_unknown_ticker(report: Report, question: Question, server: Span) -> None:
    report.check("no agent span", not question.trace.named(ANALYST_SPAN))
    report.check(
        "unknown ticker logged at WARNING", question.trace.logged("WARN", "Unknown ticker")
    )


def check_second_question(report: Report, question: Question, server: Span) -> None:
    if not question.last:
        return
    trace = question.trace
    report.check(
        "no SEC client span", not trace.sec_calls("companyfacts") and not trace.sec_calls("frames")
    )
    report.check("no facts load", not trace.logged("INFO", "Facts loaded"))


def check_outside_cache(report: Report, question: Question, server: Span) -> None:
    calls = question.trace.sec_calls("companyfacts")
    report.check(
        "companyfacts client span under the server span",
        len(calls) == 1 and calls[0].parent_id == server.span_id,
    )
    report.check("facts loaded from the SEC logged", question.trace.logged("INFO", "from sec"))


def check_sec_down(report: Report, question: Question, server: Span) -> None:
    statuses = [call.status for call in question.trace.sec_calls("companyfacts")]
    report.check(
        "two failed attempts then one that succeeds",
        statuses == [ERROR, ERROR, "Unset"],
        str(statuses),
    )
    report.check("retries logged at WARNING", question.trace.logged("WARN", "retrying"))


def check_sec_unreachable(report: Report, question: Question, server: Span) -> None:
    trace = question.trace
    tools = trace.named("execute_tool frame_values")
    tool_status = question.profile.tool_status
    report.check(
        "execute_tool frame_values failed"
        + (" with gen_ai.tool.status error" if tool_status else ""),
        bool(tools)
        and all(
            tool.status == ERROR
            and (not tool_status or tool.attributes.get("gen_ai.tool.status") == "error")
            for tool in tools
        ),
    )
    calls = trace.sec_calls("frames")
    report.check(
        "four failed frames attempts",
        len(calls) == 4 and all(call.status == ERROR for call in calls),
        str(len(calls)),
    )
    analysts = trace.named(ANALYST_SPAN)
    report.check(
        "the analyst kept running",
        bool(analysts) and all(analyst.status != ERROR for analyst in analysts),
    )
    report.check("SEC failure logged at ERROR", trace.logged("ERROR", "failed after"))


def check_sec_blocked(report: Report, question: Question, server: Span) -> None:
    trace = question.trace
    calls = trace.sec_calls("companyfacts")
    if question.index == 0:
        report.check(
            "one companyfacts client span answered 403, no retry",
            len(calls) == 1
            and calls[0].attributes.get("http.status_code") == 403
            and calls[0].attributes.get("error.type") == "403",
        )
        report.check("403 logged at ERROR", trace.logged("ERROR", "403"))
    else:
        report.check("no client span inside the back-off", not calls)
        report.check(
            "back-off refusal logged at WARNING", trace.logged("WARN", "back-off in force")
        )


def check_timeout(report: Report, question: Question, server: Span) -> None:
    analyst = question.trace.one(ANALYST_SPAN)
    report.check(
        "invoke_agent analyst ended without error status",
        analyst is not None and analyst.status != ERROR,
    )
    report.check("timeout logged at WARNING", question.trace.logged("WARN", "second budget"))


def check_ungrounded_answer(report: Report, question: Question, server: Span) -> None:
    verify = question.trace.one(VERIFY_SPAN)
    report.check(
        "filing.verify_answer records the rejection",
        verify is not None and "base14.filing.rejection_reason" in verify.attributes,
    )
    report.check(
        "rejection logged at WARNING", question.trace.logged("WARN", "rejected by the verifier")
    )


def check_model_unavailable(report: Report, question: Question, server: Span) -> None:
    failure_span = question.profile.model_failure_span
    analyst = question.trace.one(ANALYST_SPAN)
    if failure_span is None:
        report.check("error invoke_agent span", analyst is not None and analyst.status == ERROR)
    else:
        chats = [
            span
            for span in question.trace.spans
            if span.name == failure_span or span.name.startswith(f"{failure_span} ")
        ]
        report.check(
            f"error {failure_span} and invoke_agent spans",
            bool(chats)
            and chats[0].status == ERROR
            and analyst is not None
            and analyst.status == ERROR,
        )
    report.check("run failure logged at ERROR", question.trace.logged("ERROR", "Run failed"))


def check_tight_budget(report: Report, question: Question, server: Span) -> None:
    """The stop can land on the reminder run, when the spent budget turned the answer tool
    away."""
    report.check(
        "invoke_agent analyst failed with BudgetExceeded",
        any(
            analyst.status == ERROR
            and str(analyst.attributes.get("error.type", "")).endswith("BudgetExceeded")
            for analyst in question.trace.named(ANALYST_SPAN)
        ),
    )
    report.check("budget logged at WARNING", question.trace.logged("WARN", "Call budget"))


def check_bad_output(report: Report, question: Question, server: Span) -> None:
    trace = question.trace
    answer_tool_span = question.profile.answer_tool_span
    if answer_tool_span is not None:
        answers = [span for span in trace.named(answer_tool_span) if span.status == ERROR]
        report.check(f"one failed {answer_tool_span} span", len(answers) == 1, str(len(answers)))
    report.check("validation failure logged at WARNING", trace.logged("WARN", "failed validation"))
    report.check("run failure logged at ERROR", trace.logged("ERROR", "Run failed"))


SCENARIO_CHECKS: dict[str, Callable[[Report, Question, Span], None]] = {
    "unknown_ticker": check_unknown_ticker,
    "second_question": check_second_question,
    "ranking": check_ranking,
    "outside_cache": check_outside_cache,
    "sec_down": check_sec_down,
    "sec_unreachable": check_sec_unreachable,
    "sec_blocked": check_sec_blocked,
    "timeout": check_timeout,
    "ungrounded_answer": check_ungrounded_answer,
    "model_unavailable": check_model_unavailable,
    "tight_budget": check_tight_budget,
    "bad_output": check_bad_output,
}
ALL_SCENARIOS = (
    "unknown_ticker",
    "single_figure",
    "ratio",
    "second_question",
    "trend",
    "restated",
    "ranking",
    "outside_cache",
    "not_in_data",
    "sec_down",
    "sec_unreachable",
    "timeout",
    "ungrounded_answer",
    "model_unavailable",
    "tight_budget",
    "bad_output",
    "sec_blocked",
)
AGENT_FAILURES = ("timeout", "model_unavailable", "tight_budget", "bad_output", "ungrounded_answer")


def verify_question(report: Report, question: Question) -> None:
    server = check_common(report, question, question.result["outcome"])
    if question.result["status"] == HTTP_OK:
        check_served(report, question, server)
    elif question.scenario in AGENT_FAILURES:
        check_agent_run(report, question, server)
    scenario_check = SCENARIO_CHECKS.get(question.scenario)
    if scenario_check is not None:
        scenario_check(report, question, server)


def verify_metrics(
    report: Report, telemetry: Telemetry, outcomes: set[str], profile: Profile
) -> None:
    emitted = {point.metric for point in telemetry.data_points}
    for name in (*APPLICATION_METRICS, *profile.metrics):
        report.check(name, name in emitted)
    recorded = {
        str(point.attributes.get(OUTCOME))
        for point in telemetry.data_points
        if point.metric == "base14.filing.questions"
    }
    report.check(
        "base14.filing.questions carries every outcome of the run",
        outcomes <= recorded,
        f"missing {sorted(outcomes - recorded)}",
    )


_SELF_METRIC = re.compile(
    r"^otelcol_exporter_(sent|send_failed)_(\w+?)(?:_total)?\{([^}]*)\}\s+(\S+)$"
)


def exporter_counts(prometheus_text: str) -> dict[tuple[str, str], float]:
    counts: dict[tuple[str, str], float] = {}
    for line in prometheus_text.splitlines():
        match = _SELF_METRIC.match(line)
        if match and f'exporter="{SCOUT_EXPORTER}"' in match.group(3):
            outcome, signal, _, value = match.groups()
            counts[outcome, signal] = counts.get((outcome, signal), 0) + float(value)
    return counts


def verify_exporter(
    report: Report, telemetry: Telemetry, prometheus_text: str, at_start_text: str | None
) -> None:
    """Send counts are the growth since test-api.sh read the cumulative counters."""
    if not prometheus_text:
        print("  SKIP no collector self-metrics given, send counts not checked")
    elif at_start_text is None:
        report.check("the harness recorded the exporter counters at the start of the run", False)
    else:
        counts = exporter_counts(prometheus_text)
        at_start = exporter_counts(at_start_text)
        for signal in SIGNALS:
            sent, failed = (
                counts.get((outcome, signal), 0) - at_start.get((outcome, signal), 0)
                for outcome in ("sent", "send_failed")
            )
            report.check(f"sent {signal} during the run: {sent:.0f}", sent > 0, "nothing sent")
            report.check(f"failed {signal} during the run: {failed:.0f}", failed == 0)
    report.check(
        "no collector warnings or errors",
        not telemetry.collector_warnings,
        "; ".join(telemetry.collector_warnings[:3]),
    )


def main(argv: list[str]) -> int:
    allow_partial = "--allow-partial" in argv
    paths = [Path(arg) for arg in argv if arg != "--allow-partial"]
    run = json.loads(paths[0].read_text())
    with paths[1].open() as lines:
        telemetry = parse(lines)
    prometheus_text = paths[2].read_text() if len(paths) > 2 else ""
    report = Report()
    framework = str(run.get("framework") or "strands")
    profile = PROFILES[framework]
    print("=== Harness run ===")
    print(f"  framework {framework}")
    ran = [result["scenario"] for result in run["scenarios"]]
    missing = [name for name in ALL_SCENARIOS if name not in ran]
    if allow_partial:
        print(f"  SKIP partial run allowed, {len(ran)} of {len(ALL_SCENARIOS)} scenarios")
    else:
        report.check(f"the run holds all {len(ALL_SCENARIOS)} scenarios", not missing, str(missing))
    report.check("the harness passed", bool(run.get("passed")))
    counts: list[tuple[str, str, int, int]] = []
    for result in run["scenarios"]:
        for index, question_id in enumerate(result["question_ids"]):
            print(f"\n=== {result['scenario']} {question_id} ===")
            trace = find_trace(telemetry, question_id)
            report.check("one trace with its server span", trace is not None)
            if trace is None:
                continue
            verify_question(
                report, Question(result["scenario"], question_id, result, trace, index, profile)
            )
            counts.append((result["scenario"], question_id, len(trace.spans), len(trace.logs)))
    print("\n=== Metrics ===")
    outcomes = {str(result["outcome"]) for result in run["scenarios"]}
    verify_metrics(report, telemetry, outcomes, profile)
    print(f"\n=== Scout exporter ({SCOUT_EXPORTER}) ===")
    verify_exporter(report, telemetry, prometheus_text, run.get("collector_self_metrics_at_start"))
    print("\n=== Spans and logs per question ===")
    for scenario, question_id, span_count, log_count in counts:
        print(f"  {scenario:<18} {question_id}  {span_count:>3} spans  {log_count:>2} logs")
    print(f"\n{report.failures} failed checks.")
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
