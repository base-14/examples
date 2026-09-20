use std::collections::VecDeque;
use std::sync::{Arc, LazyLock, Mutex, MutexGuard};
use std::time::Duration;

use opentelemetry::trace::{SpanKind, Status, TracerProvider};
use opentelemetry::{Array, KeyValue, Value, global};
use opentelemetry_sdk::metrics::data::{AggregatedMetrics, MetricData, ResourceMetrics};
use opentelemetry_sdk::metrics::{
    InMemoryMetricExporter, InMemoryMetricExporterBuilder, PeriodicReader, SdkMeterProvider,
    Temporality,
};
use opentelemetry_sdk::trace::{InMemorySpanExporter, SdkTracerProvider, SpanData};
use serde_json::Value as Json;
use tracing::Instrument;
use tracing_opentelemetry::OpenTelemetryLayer;
use tracing_subscriber::layer::SubscriberExt;

use super::{GenerateRequest, GenerateResponse, LlmClient, Provider};

const CHAT_COMPLETION: &str = include_str!("../../../../_shared/test-vectors/chat-completion.json");
const CHAT_WITH_RETRY: &str = include_str!("../../../../_shared/test-vectors/chat-with-retry.json");
const CHAT_WITH_FALLBACK: &str =
    include_str!("../../../../_shared/test-vectors/chat-with-fallback.json");

const OLLAMA_BASE_URL: &str = "http://localhost:11434";

struct Telemetry {
    spans: InMemorySpanExporter,
    metrics: InMemoryMetricExporter,
    tracer_provider: SdkTracerProvider,
    meter_provider: SdkMeterProvider,
}

static TELEMETRY: LazyLock<Telemetry> = LazyLock::new(|| {
    let spans = InMemorySpanExporter::default();
    let tracer_provider = SdkTracerProvider::builder()
        .with_simple_exporter(spans.clone())
        .build();

    let metrics = InMemoryMetricExporterBuilder::new()
        .with_temporality(Temporality::Delta)
        .build();
    let reader = PeriodicReader::builder(metrics.clone())
        .with_interval(Duration::from_secs(3600))
        .build();
    let meter_provider = SdkMeterProvider::builder().with_reader(reader).build();
    global::set_meter_provider(meter_provider.clone());

    Telemetry {
        spans,
        metrics,
        tracer_provider,
        meter_provider,
    }
});

static SERIAL: Mutex<()> = Mutex::new(());

/// Exclusive access to the in-memory exporters for the length of one test.
struct Recording {
    _serial: MutexGuard<'static, ()>,
    _subscriber: tracing::subscriber::DefaultGuard,
}

impl Recording {
    fn start() -> Self {
        let serial = SERIAL
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());

        TELEMETRY.meter_provider.force_flush().unwrap();
        TELEMETRY.metrics.reset();
        TELEMETRY.spans.reset();

        let layer = OpenTelemetryLayer::new(TELEMETRY.tracer_provider.tracer("vector-tests"));
        let subscriber = tracing_subscriber::registry().with(layer);

        Self {
            _serial: serial,
            _subscriber: tracing::subscriber::set_default(subscriber),
        }
    }

    fn spans(&self) -> Vec<SpanData> {
        TELEMETRY.spans.get_finished_spans().unwrap()
    }

    fn metrics(&self) -> Vec<ResourceMetrics> {
        TELEMETRY.meter_provider.force_flush().unwrap();
        TELEMETRY.metrics.get_finished_metrics().unwrap()
    }
}

type Outcome = Result<GenerateResponse, String>;

struct ScriptedProvider {
    name: &'static str,
    outcomes: Mutex<VecDeque<Outcome>>,
}

fn scripted(name: &'static str, outcomes: Vec<Outcome>) -> Arc<dyn Provider> {
    Arc::new(ScriptedProvider {
        name,
        outcomes: Mutex::new(outcomes.into()),
    })
}

#[async_trait::async_trait]
impl Provider for ScriptedProvider {
    async fn generate(&self, _req: &GenerateRequest) -> anyhow::Result<GenerateResponse> {
        match self.outcomes.lock().unwrap().pop_front() {
            Some(Ok(response)) => Ok(response),
            Some(Err(message)) => Err(anyhow::anyhow!(message)),
            None => panic!(
                "{} was called more often than the vector scripts",
                self.name
            ),
        }
    }
}

fn response_from(mock: &Json) -> GenerateResponse {
    GenerateResponse {
        content: mock["content"].as_str().unwrap().to_string(),
        model: mock["model"].as_str().unwrap().to_string(),
        response_id: mock["response_id"].as_str().map(str::to_string),
        input_tokens: mock["input_tokens"].as_u64().unwrap() as u32,
        output_tokens: mock["output_tokens"].as_u64().unwrap() as u32,
        cost_usd: 0.0,
        finish_reason: mock["finish_reason"]
            .as_str()
            .unwrap_or_default()
            .to_string(),
        provider: String::new(),
    }
}

fn request(
    model: &str,
    prompt: &str,
    system: &str,
    temperature: f64,
    max_tokens: u32,
) -> GenerateRequest {
    GenerateRequest {
        model: model.to_string(),
        system: system.to_string(),
        prompt: prompt.to_string(),
        temperature,
        max_tokens,
        stage: "analyze".to_string(),
    }
}

fn find_span<'a>(spans: &'a [SpanData], name: &str) -> &'a SpanData {
    spans
        .iter()
        .find(|span| span.name == name)
        .unwrap_or_else(|| {
            let names: Vec<&str> = spans.iter().map(|span| span.name.as_ref()).collect();
            panic!("span {name:?} not found in {names:?}")
        })
}

fn attribute<'a>(span: &'a SpanData, key: &str) -> Option<&'a Value> {
    span.attributes
        .iter()
        .find(|kv| kv.key.as_str() == key)
        .map(|kv| &kv.value)
}

fn numeric(value: &Value) -> Option<f64> {
    match value {
        Value::F64(v) => Some(*v),
        Value::I64(v) => Some(*v as f64),
        _ => None,
    }
}

fn assert_attributes(span: &SpanData, expected: &Json) {
    for (key, want) in expected.as_object().unwrap() {
        let got = attribute(span, key)
            .unwrap_or_else(|| panic!("span {} has no attribute {key}", span.name));

        match want {
            Json::String(want) => assert_eq!(got.as_str(), want.as_str(), "attribute {key}"),
            Json::Number(want) => {
                let want = want.as_f64().unwrap();
                let got = numeric(got).unwrap_or_else(|| panic!("attribute {key} is not numeric"));
                assert!(
                    (got - want).abs() <= want.abs() * 0.01,
                    "attribute {key}: expected {want}, got {got}"
                );
            }
            Json::Array(want) => {
                let Value::Array(Array::String(got)) = got else {
                    panic!("attribute {key} is not a string array")
                };
                let got: Vec<&str> = got.iter().map(|item| item.as_str()).collect();
                let want: Vec<&str> = want.iter().map(|item| item.as_str().unwrap()).collect();
                assert_eq!(got, want, "attribute {key}");
            }
            other => panic!("unsupported expectation for {key}: {other}"),
        }
    }
}

fn event_names(span: &SpanData) -> Vec<&str> {
    span.events
        .iter()
        .map(|event| event.name.as_ref())
        .collect()
}

fn event_attribute<'a>(span: &'a SpanData, event_name: &str, key: &str) -> &'a Value {
    let event = span
        .events
        .iter()
        .find(|event| event.name == event_name)
        .unwrap_or_else(|| panic!("event {event_name} not found on span {}", span.name));
    event
        .attributes
        .iter()
        .find(|kv| kv.key.as_str() == key)
        .map(|kv| &kv.value)
        .unwrap_or_else(|| panic!("event {event_name} has no attribute {key}"))
}

trait ToF64 {
    fn to_f64(self) -> f64;
}

impl ToF64 for f64 {
    fn to_f64(self) -> f64 {
        self
    }
}

impl ToF64 for u64 {
    fn to_f64(self) -> f64 {
        self as f64
    }
}

impl ToF64 for i64 {
    fn to_f64(self) -> f64 {
        self as f64
    }
}

fn matches_attrs<'a>(attrs: impl Iterator<Item = &'a KeyValue>, expected: &[(&str, &str)]) -> bool {
    let attrs: Vec<&KeyValue> = attrs.collect();
    expected.iter().all(|(key, value)| {
        attrs
            .iter()
            .any(|kv| kv.key.as_str() == *key && kv.value.to_string() == *value)
    })
}

fn data_total<T: Copy + ToF64>(data: &MetricData<T>, expected: &[(&str, &str)]) -> f64 {
    match data {
        MetricData::Sum(sum) => sum
            .data_points()
            .filter(|point| matches_attrs(point.attributes(), expected))
            .map(|point| point.value().to_f64())
            .sum(),
        MetricData::Histogram(histogram) => histogram
            .data_points()
            .filter(|point| matches_attrs(point.attributes(), expected))
            .map(|point| point.sum().to_f64())
            .sum(),
        _ => 0.0,
    }
}

fn data_count<T: Copy + ToF64>(data: &MetricData<T>, expected: &[(&str, &str)]) -> u64 {
    match data {
        MetricData::Histogram(histogram) => histogram
            .data_points()
            .filter(|point| matches_attrs(point.attributes(), expected))
            .map(|point| point.count())
            .sum(),
        _ => 0,
    }
}

fn metric_total(metrics: &[ResourceMetrics], name: &str, expected: &[(&str, &str)]) -> f64 {
    let mut total = 0.0;
    for resource in metrics {
        for scope in resource.scope_metrics() {
            for metric in scope.metrics().filter(|metric| metric.name() == name) {
                total += match metric.data() {
                    AggregatedMetrics::F64(data) => data_total(data, expected),
                    AggregatedMetrics::U64(data) => data_total(data, expected),
                    AggregatedMetrics::I64(data) => data_total(data, expected),
                };
            }
        }
    }
    total
}

fn metric_count(metrics: &[ResourceMetrics], name: &str, expected: &[(&str, &str)]) -> u64 {
    let mut count = 0;
    for resource in metrics {
        for scope in resource.scope_metrics() {
            for metric in scope.metrics().filter(|metric| metric.name() == name) {
                count += match metric.data() {
                    AggregatedMetrics::F64(data) => data_count(data, expected),
                    AggregatedMetrics::U64(data) => data_count(data, expected),
                    AggregatedMetrics::I64(data) => data_count(data, expected),
                };
            }
        }
    }
    count
}

fn is_error(status: &Status) -> bool {
    matches!(status, Status::Error { .. })
}

#[tokio::test(start_paused = true)]
async fn chat_completion_vector_records_span_attributes_and_metrics() {
    let vector: Json = serde_json::from_str(CHAT_COMPLETION).unwrap();
    let input = &vector["input"];
    let mock = &vector["mock_response"];
    let expected = &vector["expected_span"];
    let model = input["model"].as_str().unwrap();

    let recording = Recording::start();

    let client = LlmClient {
        primary: scripted("anthropic", vec![Ok(response_from(mock))]),
        fallback: None,
        primary_provider: "anthropic".to_string(),
        fallback_provider: "openai".to_string(),
        fallback_model: "gpt-4.1-mini".to_string(),
        ollama_base_url: OLLAMA_BASE_URL.to_string(),
        capture_content: false,
    };

    let response = client
        .generate(&request(
            model,
            input["prompt"].as_str().unwrap(),
            input["system"].as_str().unwrap(),
            input["temperature"].as_f64().unwrap(),
            input["max_tokens"].as_u64().unwrap() as u32,
        ))
        .await
        .unwrap();

    assert_eq!(response.content, mock["content"].as_str().unwrap());

    let spans = recording.spans();
    let span = find_span(&spans, expected["name"].as_str().unwrap());
    assert_eq!(span.span_kind, SpanKind::Client);
    assert!(!is_error(&span.status));
    assert_attributes(span, &expected["attributes"]);
    assert!(
        event_names(span).is_empty(),
        "content capture is off, so the span carries no inference event"
    );

    let metrics = recording.metrics();
    let base = [
        ("gen_ai.operation.name", "chat"),
        ("gen_ai.provider.name", "anthropic"),
        ("gen_ai.request.model", model),
    ];
    let mut input_attrs = base.to_vec();
    input_attrs.push(("gen_ai.token.type", "input"));
    let mut output_attrs = base.to_vec();
    output_attrs.push(("gen_ai.token.type", "output"));

    assert_eq!(
        metric_total(&metrics, "gen_ai.client.token.usage", &input_attrs),
        mock["input_tokens"].as_f64().unwrap()
    );
    assert_eq!(
        metric_total(&metrics, "gen_ai.client.token.usage", &output_attrs),
        mock["output_tokens"].as_f64().unwrap()
    );
    assert_eq!(
        metric_count(&metrics, "gen_ai.client.operation.duration", &base),
        1
    );

    let expected_cost = expected["attributes"]["base14.gen_ai.cost_usd"]
        .as_f64()
        .unwrap();
    let cost = metric_total(&metrics, "base14.gen_ai.cost", &base);
    assert!((cost - expected_cost).abs() <= expected_cost * 0.01);

    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.retry.count", &[]),
        0.0
    );
    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.fallback.count", &[]),
        0.0
    );
    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.error.count", &[]),
        0.0
    );
}

#[tokio::test(start_paused = true)]
async fn chat_completion_vector_emits_the_inference_event_when_capture_is_on() {
    let vector: Json = serde_json::from_str(CHAT_COMPLETION).unwrap();
    let input = &vector["input"];
    let mock = &vector["mock_response"];
    let expected_event = vector["expected_span"]["events"][0]["name"]
        .as_str()
        .unwrap();

    let recording = Recording::start();

    let client = LlmClient {
        primary: scripted("anthropic", vec![Ok(response_from(mock))]),
        fallback: None,
        primary_provider: "anthropic".to_string(),
        fallback_provider: "openai".to_string(),
        fallback_model: "gpt-4.1-mini".to_string(),
        ollama_base_url: OLLAMA_BASE_URL.to_string(),
        capture_content: true,
    };

    client
        .generate(&request(
            input["model"].as_str().unwrap(),
            input["prompt"].as_str().unwrap(),
            input["system"].as_str().unwrap(),
            input["temperature"].as_f64().unwrap(),
            input["max_tokens"].as_u64().unwrap() as u32,
        ))
        .await
        .unwrap();

    let spans = recording.spans();
    let span = find_span(&spans, vector["expected_span"]["name"].as_str().unwrap());

    assert_eq!(event_names(span), vec![expected_event]);
    assert_eq!(
        event_attribute(span, expected_event, "gen_ai.input.messages").as_str(),
        input["prompt"].as_str().unwrap()
    );
    assert_eq!(
        event_attribute(span, expected_event, "gen_ai.system_instructions").as_str(),
        input["system"].as_str().unwrap()
    );
    assert_eq!(
        event_attribute(span, expected_event, "gen_ai.output.messages").as_str(),
        mock["content"].as_str().unwrap()
    );
}

#[tokio::test(start_paused = true)]
async fn chat_with_retry_vector_keeps_the_retry_inside_one_span() {
    let vector: Json = serde_json::from_str(CHAT_WITH_RETRY).unwrap();
    let setup = &vector["setup"];
    let behavior = &vector["mock_behavior"];
    let expected = &vector["expected_span"];
    assert!(
        behavior["attempt_1"]
            .as_str()
            .unwrap()
            .contains("Rate limit")
    );

    let recording = Recording::start();

    let client = LlmClient {
        primary: scripted(
            "anthropic",
            vec![
                Err("Rate limit".to_string()),
                Ok(response_from(&behavior["attempt_2"])),
            ],
        ),
        fallback: None,
        primary_provider: setup["provider"].as_str().unwrap().to_string(),
        fallback_provider: setup["fallback_provider"].as_str().unwrap().to_string(),
        fallback_model: setup["fallback_model"].as_str().unwrap().to_string(),
        ollama_base_url: OLLAMA_BASE_URL.to_string(),
        capture_content: false,
    };

    let response = client
        .generate(&request(
            setup["model"].as_str().unwrap(),
            "Hello",
            "You are helpful.",
            0.7,
            1024,
        ))
        .await
        .unwrap();

    assert_eq!(
        response.content,
        behavior["attempt_2"]["content"].as_str().unwrap()
    );

    let spans = recording.spans();
    let span = find_span(&spans, expected["name"].as_str().unwrap());
    assert!(
        !is_error(&span.status),
        "the retry is transparent to the caller"
    );
    assert_attributes(span, &expected["attributes"]);
    assert_eq!(spans.len(), 1, "the retry shares the span of the call");

    let metrics = recording.metrics();
    // The vector names the Python exception class; this client records an error code.
    let retry_attrs = [
        ("gen_ai.provider.name", "anthropic"),
        ("error.type", "rate_limit"),
        ("base14.retry.attempt", "1"),
    ];
    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.retry.count", &retry_attrs),
        1.0
    );
    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.fallback.count", &[]),
        0.0
    );
    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.error.count", &[]),
        0.0
    );
}

#[tokio::test(start_paused = true)]
async fn chat_with_fallback_vector_switches_provider_without_failing_the_parent() {
    let vector: Json = serde_json::from_str(CHAT_WITH_FALLBACK).unwrap();
    let setup = &vector["setup"];
    let primary_model = setup["primary_model"].as_str().unwrap();
    let fallback_model = setup["fallback_model"].as_str().unwrap();
    let expected_primary = &vector["expected_spans"][0];
    let expected_fallback = &vector["expected_spans"][1];

    let recording = Recording::start();

    let failures = vec![
        Err("Service unavailable".to_string()),
        Err("Service unavailable".to_string()),
        Err("Service unavailable".to_string()),
    ];
    let client = LlmClient {
        primary: scripted("anthropic", failures),
        fallback: Some(scripted(
            "openai",
            vec![Ok(response_from(&vector["mock_behavior"]["fallback"]))],
        )),
        primary_provider: setup["primary_provider"].as_str().unwrap().to_string(),
        fallback_provider: setup["fallback_provider"].as_str().unwrap().to_string(),
        fallback_model: fallback_model.to_string(),
        ollama_base_url: OLLAMA_BASE_URL.to_string(),
        capture_content: false,
    };

    let parent = tracing::info_span!("pipeline.run");
    let response = client
        .generate(&request(
            primary_model,
            "Hello",
            "You are helpful.",
            0.7,
            1024,
        ))
        .instrument(parent.clone())
        .await
        .unwrap();
    drop(parent);

    assert_eq!(
        response.content,
        vector["mock_behavior"]["fallback"]["content"]
            .as_str()
            .unwrap()
    );

    let spans = recording.spans();

    let primary_span = find_span(&spans, expected_primary["name"].as_str().unwrap());
    assert!(is_error(&primary_span.status));
    // The vector names the Python exception class; this client records an error code.
    assert_eq!(
        attribute(primary_span, "error.type").unwrap().as_str(),
        "server_error"
    );
    assert_eq!(
        attribute(primary_span, "gen_ai.provider.name")
            .unwrap()
            .as_str(),
        expected_primary["attributes"]["gen_ai.provider.name"]
            .as_str()
            .unwrap()
    );
    assert_eq!(event_names(primary_span), vec!["exception"]);

    let fallback_span = find_span(&spans, expected_fallback["name"].as_str().unwrap());
    assert!(!is_error(&fallback_span.status));
    assert_attributes(fallback_span, &expected_fallback["attributes"]);

    let parent_span = find_span(&spans, "pipeline.run");
    assert!(!is_error(&parent_span.status));
    assert_eq!(
        attribute(parent_span, "gen_ai.fallback.triggered").unwrap(),
        &Value::Bool(true)
    );
    assert_eq!(
        event_attribute(
            parent_span,
            "provider_fallback",
            "base14.gen_ai.fallback.provider"
        )
        .as_str(),
        setup["fallback_provider"].as_str().unwrap()
    );

    let metrics = recording.metrics();
    let expected_metrics: Vec<&Json> = vector["expected_metrics"]
        .as_array()
        .unwrap()
        .iter()
        .collect();
    let expected_value = |name: &str| -> f64 {
        expected_metrics
            .iter()
            .find(|metric| metric["name"] == name)
            .unwrap()["value"]
            .as_f64()
            .unwrap()
    };

    assert_eq!(
        metric_total(&metrics, "base14.gen_ai.retry.count", &[]),
        expected_value("base14.gen_ai.retry.count")
    );
    assert_eq!(
        metric_total(
            &metrics,
            "base14.gen_ai.fallback.count",
            &[
                ("gen_ai.provider.name", "anthropic"),
                ("base14.gen_ai.fallback.provider", "openai"),
            ]
        ),
        expected_value("base14.gen_ai.fallback.count")
    );
    assert_eq!(
        metric_total(
            &metrics,
            "base14.gen_ai.error.count",
            &[
                ("gen_ai.provider.name", "anthropic"),
                ("error.type", "server_error"),
            ]
        ),
        expected_value("base14.gen_ai.error.count")
    );

    assert_eq!(
        metric_total(
            &metrics,
            "gen_ai.client.token.usage",
            &[("gen_ai.request.model", primary_model)]
        ),
        0.0,
        "the failed primary call records no token usage"
    );
    assert!(
        metric_total(
            &metrics,
            "gen_ai.client.token.usage",
            &[("gen_ai.request.model", fallback_model)]
        ) > 0.0
    );
    assert!(
        metric_total(
            &metrics,
            "base14.gen_ai.cost",
            &[("gen_ai.request.model", fallback_model)]
        ) > 0.0
    );
}
