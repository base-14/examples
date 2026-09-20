use std::sync::Arc;
use std::time::{Duration, Instant};

use opentelemetry::trace::Status;
use opentelemetry::{Array, KeyValue, StringValue, Value};
use tracing::{Instrument, Span};
use tracing_opentelemetry::OpenTelemetrySpanExt;

use super::content::{COMPLETION_MAX_CHARS, PROMPT_MAX_CHARS, SYSTEM_MAX_CHARS, scrub, truncate};
use super::pricing::calculate_cost;
use super::provider::{endpoint, semconv_name};
use super::{GenerateRequest, GenerateResponse, Provider};
use crate::telemetry::metrics::{
    GEN_AI_COST, GEN_AI_ERROR_COUNT, GEN_AI_FALLBACK_COUNT, GEN_AI_OPERATION_DURATION,
    GEN_AI_RETRY_COUNT, GEN_AI_TOKEN_USAGE,
};

const MAX_ATTEMPTS: u32 = 3;
const RETRY_MIN_DELAY: Duration = Duration::from_secs(1);
const RETRY_MAX_DELAY: Duration = Duration::from_secs(10);

pub struct LlmClient {
    pub primary: Arc<dyn Provider>,
    pub fallback: Option<Arc<dyn Provider>>,
    pub primary_provider: String,
    pub fallback_provider: String,
    pub fallback_model: String,
    pub ollama_base_url: String,
    pub capture_content: bool,
}

impl LlmClient {
    pub async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GenerateResponse> {
        let primary_err = match self
            .chat(self.primary.as_ref(), &self.primary_provider, req)
            .await
        {
            Ok(resp) => return Ok(resp),
            Err(err) => err,
        };

        let Some(fallback) = self.fallback.as_ref() else {
            return Err(anyhow::anyhow!(
                "primary provider {} failed after retries: {}",
                self.primary_provider,
                primary_err
            ));
        };

        self.record_fallback(&primary_err);

        let fallback_req = GenerateRequest {
            model: self.fallback_model.clone(),
            ..req.clone()
        };

        self.chat(fallback.as_ref(), &self.fallback_provider, &fallback_req)
            .await
    }

    async fn chat(
        &self,
        provider: &dyn Provider,
        provider_name: &str,
        req: &GenerateRequest,
    ) -> anyhow::Result<GenerateResponse> {
        let semconv_provider = semconv_name(provider_name);
        let (server_address, server_port) = endpoint(provider_name, &self.ollama_base_url);

        let span = tracing::info_span!(
            "chat",
            otel.name = %format!("chat {}", req.model),
            otel.kind = "client",
            gen_ai.operation.name = "chat",
            gen_ai.provider.name = semconv_provider,
            gen_ai.request.model = %req.model,
            server.address = %server_address,
            server.port = server_port,
            gen_ai.request.temperature = req.temperature,
            gen_ai.request.max_tokens = req.max_tokens as i64,
            gen_ai.response.model = tracing::field::Empty,
            gen_ai.response.id = tracing::field::Empty,
            gen_ai.usage.input_tokens = tracing::field::Empty,
            gen_ai.usage.output_tokens = tracing::field::Empty,
            base14.gen_ai.cost_usd = tracing::field::Empty,
            base14.report.stage = %req.stage,
            error.type = tracing::field::Empty,
        );

        let operation_attrs = [
            KeyValue::new("gen_ai.operation.name", "chat"),
            KeyValue::new("gen_ai.provider.name", semconv_provider),
            KeyValue::new("gen_ai.request.model", req.model.clone()),
        ];

        let start = Instant::now();
        let result = self
            .attempt_with_retries(provider, semconv_provider, req, &span)
            .await;
        let duration = start.elapsed().as_secs_f64();

        match result {
            Ok(mut resp) => {
                resp.provider = provider_name.to_string();
                resp.cost_usd = calculate_cost(&resp.model, resp.input_tokens, resp.output_tokens);

                span.record("gen_ai.response.model", resp.model.as_str());
                if let Some(id) = resp.response_id.as_deref() {
                    span.record("gen_ai.response.id", id);
                }
                if !resp.finish_reason.is_empty() {
                    span.set_attribute(
                        "gen_ai.response.finish_reasons",
                        Value::Array(Array::String(vec![StringValue::from(
                            resp.finish_reason.clone(),
                        )])),
                    );
                }
                span.record("gen_ai.usage.input_tokens", i64::from(resp.input_tokens));
                span.record("gen_ai.usage.output_tokens", i64::from(resp.output_tokens));
                span.record("base14.gen_ai.cost_usd", resp.cost_usd);

                self.emit_content_event(&span, req, Some(&resp));

                GEN_AI_TOKEN_USAGE.record(
                    f64::from(resp.input_tokens),
                    &with_attr(
                        &operation_attrs,
                        KeyValue::new("gen_ai.token.type", "input"),
                    ),
                );
                GEN_AI_TOKEN_USAGE.record(
                    f64::from(resp.output_tokens),
                    &with_attr(
                        &operation_attrs,
                        KeyValue::new("gen_ai.token.type", "output"),
                    ),
                );
                GEN_AI_OPERATION_DURATION.record(duration, &operation_attrs);
                GEN_AI_COST.add(resp.cost_usd, &operation_attrs);

                Ok(resp)
            }
            Err(err) => {
                let error_type = classify_error(&err);

                span.add_event(
                    "exception",
                    vec![
                        KeyValue::new("exception.type", error_type),
                        KeyValue::new("exception.message", err.to_string()),
                    ],
                );
                span.record("error.type", error_type);
                span.set_status(Status::error(err.to_string()));

                self.emit_content_event(&span, req, None);

                let error_attrs =
                    with_attr(&operation_attrs, KeyValue::new("error.type", error_type));
                GEN_AI_OPERATION_DURATION.record(duration, &error_attrs);
                GEN_AI_ERROR_COUNT.add(1, &error_attrs);

                Err(err)
            }
        }
    }

    async fn attempt_with_retries(
        &self,
        provider: &dyn Provider,
        semconv_provider: &'static str,
        req: &GenerateRequest,
        span: &Span,
    ) -> anyhow::Result<GenerateResponse> {
        let mut last_err = None;

        for attempt in 0..MAX_ATTEMPTS {
            match provider.generate(req).instrument(span.clone()).await {
                Ok(resp) => return Ok(resp),
                Err(err) => {
                    let retry = attempt + 1 < MAX_ATTEMPTS;
                    tracing::warn!(
                        attempt = attempt + 1,
                        max_attempts = MAX_ATTEMPTS,
                        provider = semconv_provider,
                        model = %req.model,
                        error = %err,
                        will_retry = retry,
                        "LLM call failed"
                    );

                    if retry {
                        GEN_AI_RETRY_COUNT.add(
                            1,
                            &[
                                KeyValue::new("gen_ai.provider.name", semconv_provider),
                                KeyValue::new("error.type", classify_error(&err)),
                                KeyValue::new("base14.retry.attempt", i64::from(attempt + 1)),
                            ],
                        );
                    }

                    last_err = Some(err);

                    if retry {
                        tokio::time::sleep(backoff(attempt)).await;
                    }
                }
            }
        }

        Err(last_err.unwrap_or_else(|| anyhow::anyhow!("all retries exhausted")))
    }

    fn record_fallback(&self, err: &anyhow::Error) {
        let attrs = vec![
            KeyValue::new("gen_ai.provider.name", semconv_name(&self.primary_provider)),
            KeyValue::new(
                "base14.gen_ai.fallback.provider",
                semconv_name(&self.fallback_provider),
            ),
            KeyValue::new("error.type", classify_error(err)),
        ];

        tracing::warn!(
            primary_provider = %self.primary_provider,
            fallback_provider = %self.fallback_provider,
            error = %err,
            "Primary provider failed, falling back"
        );

        let span = Span::current();
        span.add_event("provider_fallback", attrs.clone());
        span.set_attribute("gen_ai.fallback.triggered", true);

        GEN_AI_FALLBACK_COUNT.add(1, &attrs);
    }

    fn emit_content_event(
        &self,
        span: &Span,
        req: &GenerateRequest,
        resp: Option<&GenerateResponse>,
    ) {
        if !self.capture_content {
            return;
        }

        let mut attrs = vec![KeyValue::new(
            "gen_ai.input.messages",
            truncate(&scrub(&req.prompt), PROMPT_MAX_CHARS),
        )];

        let system_instructions = truncate(&scrub(&req.system), SYSTEM_MAX_CHARS);
        if !system_instructions.is_empty() {
            attrs.push(KeyValue::new(
                "gen_ai.system_instructions",
                system_instructions,
            ));
        }

        if let Some(resp) = resp {
            attrs.push(KeyValue::new(
                "gen_ai.output.messages",
                truncate(&scrub(&resp.content), COMPLETION_MAX_CHARS),
            ));
        }

        span.add_event("gen_ai.client.inference.operation.details", attrs);
    }
}

fn with_attr(base: &[KeyValue; 3], extra: KeyValue) -> Vec<KeyValue> {
    let mut attrs = base.to_vec();
    attrs.push(extra);
    attrs
}

fn backoff(attempt: u32) -> Duration {
    let base = (RETRY_MIN_DELAY * 2u32.pow(attempt)).min(RETRY_MAX_DELAY);
    let jitter_ms = fastrand::u64(0..=base.as_millis() as u64 / 4);
    base + Duration::from_millis(jitter_ms)
}

fn classify_error(err: &anyhow::Error) -> &'static str {
    let msg = err.to_string().to_lowercase();
    if msg.contains("rate limit") || msg.contains("429") {
        "rate_limit"
    } else if msg.contains("timeout") || msg.contains("timed out") || msg.contains("deadline") {
        "timeout"
    } else if msg.contains("401")
        || msg.contains("403")
        || msg.contains("auth")
        || msg.contains("api key")
    {
        "auth_error"
    } else if msg.contains("400") || msg.contains("422") || msg.contains("invalid") {
        "invalid_request"
    } else if msg.contains("500")
        || msg.contains("502")
        || msg.contains("503")
        || msg.contains("unavailable")
        || msg.contains("server")
    {
        "server_error"
    } else if msg.contains("connect")
        || msg.contains("dns")
        || msg.contains("network")
        || msg.contains("reset")
    {
        "network_error"
    } else {
        "unknown_error"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_error_maps_messages_to_error_codes() {
        let cases = vec![
            ("rate limit exceeded", "rate_limit"),
            ("status 429: too many requests", "rate_limit"),
            ("context deadline exceeded: timeout", "timeout"),
            ("request timed out", "timeout"),
            ("401 unauthorized", "auth_error"),
            ("403 forbidden", "auth_error"),
            ("authentication failed", "auth_error"),
            ("invalid api key", "auth_error"),
            ("400 bad request", "invalid_request"),
            ("422 unprocessable entity", "invalid_request"),
            ("invalid model name", "invalid_request"),
            ("500 internal server error", "server_error"),
            ("502 bad gateway", "server_error"),
            ("503 service unavailable", "server_error"),
            ("Service unavailable", "server_error"),
            ("connection refused", "network_error"),
            ("dns resolution failed", "network_error"),
            ("connection reset by peer", "network_error"),
            ("something unexpected", "unknown_error"),
        ];

        for (msg, expected) in cases {
            let err = anyhow::anyhow!("{}", msg);
            assert_eq!(
                classify_error(&err),
                expected,
                "classify_error({msg:?}) should be {expected:?}"
            );
        }
    }

    #[test]
    fn backoff_grows_and_is_capped() {
        assert!(backoff(0) >= Duration::from_secs(1));
        assert!(backoff(0) < Duration::from_millis(1500));
        assert!(backoff(1) >= Duration::from_secs(2));
        assert!(backoff(8) <= Duration::from_millis(12_500));
    }
}
