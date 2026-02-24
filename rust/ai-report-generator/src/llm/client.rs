use std::sync::Arc;
use std::time::{Duration, Instant};

use opentelemetry::KeyValue;
use tracing::Instrument;
use tracing_opentelemetry::OpenTelemetrySpanExt;

use super::pricing::{PROVIDER_PORTS, PROVIDER_SERVERS, calculate_cost};
use super::{GenerateRequest, GenerateResponse, Provider};
use crate::telemetry::metrics::{
    GEN_AI_COST, GEN_AI_ERROR_COUNT, GEN_AI_FALLBACK_COUNT, GEN_AI_OPERATION_DURATION,
    GEN_AI_RETRY_COUNT, GEN_AI_TOKEN_USAGE,
};

pub struct LlmClient {
    pub primary: Arc<dyn Provider>,
    pub fallback: Option<Arc<dyn Provider>>,
    pub primary_provider: String,
    pub fallback_provider: String,
    pub fallback_model: String,
}

impl LlmClient {
    pub async fn generate_once(
        &self,
        provider: &dyn Provider,
        provider_name: &str,
        req: &GenerateRequest,
    ) -> anyhow::Result<GenerateResponse> {
        let span_display_name = format!("gen_ai.chat {}", req.model);
        let start = Instant::now();

        let server_addr = PROVIDER_SERVERS
            .get(provider_name)
            .copied()
            .unwrap_or("unknown");
        let server_port = PROVIDER_PORTS.get(provider_name).copied().unwrap_or(443);

        let span = tracing::info_span!(
            "gen_ai.chat",
            otel.name = %span_display_name,
            gen_ai.operation.name = "chat",
            gen_ai.provider.name = %provider_name,
            gen_ai.request.model = %req.model,
            server.address = %server_addr,
            server.port = server_port,
            gen_ai.request.temperature = req.temperature,
            gen_ai.request.max_tokens = req.max_tokens as i64,
            gen_ai.response.model = tracing::field::Empty,
            gen_ai.usage.input_tokens = tracing::field::Empty,
            gen_ai.usage.output_tokens = tracing::field::Empty,
            gen_ai.usage.cost_usd = tracing::field::Empty,
            gen_ai.response.finish_reasons = tracing::field::Empty,
            report.stage = %req.stage,
            otel.status_code = tracing::field::Empty,
            error.type = tracing::field::Empty,
        );

        {
            let mut user_event_attrs =
                vec![KeyValue::new("gen_ai.prompt", truncate(&req.prompt, 1000))];
            if !req.system.is_empty() {
                user_event_attrs.push(KeyValue::new(
                    "gen_ai.system_instructions",
                    truncate(&req.system, 500),
                ));
            }
            span.add_event("gen_ai.user.message", user_event_attrs);
        }

        let result = provider.generate(req).instrument(span.clone()).await;

        let duration = start.elapsed().as_secs_f64();

        match result {
            Ok(mut resp) => {
                resp.cost_usd = calculate_cost(&resp.model, resp.input_tokens, resp.output_tokens);

                span.record("gen_ai.response.model", resp.model.as_str());
                span.record("gen_ai.usage.input_tokens", resp.input_tokens as i64);
                span.record("gen_ai.usage.output_tokens", resp.output_tokens as i64);
                span.record("gen_ai.usage.cost_usd", resp.cost_usd);
                if !resp.finish_reason.is_empty() {
                    span.record(
                        "gen_ai.response.finish_reasons",
                        resp.finish_reason.as_str(),
                    );
                }

                span.add_event(
                    "gen_ai.assistant.message",
                    vec![KeyValue::new(
                        "gen_ai.completion",
                        truncate(&resp.content, 2000),
                    )],
                );

                let op_kv = KeyValue::new("gen_ai.operation.name", "chat");
                let provider_kv = KeyValue::new("gen_ai.provider.name", provider_name.to_string());
                let model_kv = KeyValue::new("gen_ai.request.model", resp.model.clone());

                GEN_AI_TOKEN_USAGE.record(
                    f64::from(resp.input_tokens),
                    &[
                        KeyValue::new("gen_ai.token.type", "input"),
                        op_kv.clone(),
                        provider_kv.clone(),
                        model_kv.clone(),
                    ],
                );
                GEN_AI_TOKEN_USAGE.record(
                    f64::from(resp.output_tokens),
                    &[
                        KeyValue::new("gen_ai.token.type", "output"),
                        op_kv.clone(),
                        provider_kv.clone(),
                        model_kv.clone(),
                    ],
                );
                GEN_AI_OPERATION_DURATION.record(
                    duration,
                    &[op_kv.clone(), provider_kv.clone(), model_kv.clone()],
                );
                GEN_AI_COST.add(resp.cost_usd, &[op_kv, provider_kv, model_kv]);

                Ok(resp)
            }
            Err(err) => {
                span.record("otel.status_code", "ERROR");
                span.record("error.type", err.to_string().as_str());

                GEN_AI_ERROR_COUNT.add(
                    1,
                    &[
                        KeyValue::new("gen_ai.provider.name", provider_name.to_string()),
                        KeyValue::new("gen_ai.request.model", req.model.clone()),
                    ],
                );

                Err(err)
            }
        }
    }

    pub async fn generate_with_retry(
        &self,
        provider: &dyn Provider,
        provider_name: &str,
        req: &GenerateRequest,
    ) -> anyhow::Result<GenerateResponse> {
        let max_retries: u32 = 3;
        let mut last_err = None;

        for attempt in 0..max_retries {
            match self.generate_once(provider, provider_name, req).await {
                Ok(resp) => return Ok(resp),
                Err(err) => {
                    tracing::warn!(
                        attempt = attempt + 1,
                        max_retries = max_retries,
                        provider = provider_name,
                        model = %req.model,
                        error = %err,
                        "LLM call failed, retrying"
                    );

                    if attempt > 0 {
                        GEN_AI_RETRY_COUNT.add(
                            1,
                            &[
                                KeyValue::new("gen_ai.provider.name", provider_name.to_string()),
                                KeyValue::new("gen_ai.request.model", req.model.clone()),
                            ],
                        );
                    }

                    last_err = Some(err);

                    if attempt < max_retries - 1 {
                        let delay = Duration::from_secs(1) * 2u32.pow(attempt);
                        let delay = delay.min(Duration::from_secs(10));
                        tokio::time::sleep(delay).await;
                    }
                }
            }
        }

        Err(last_err.unwrap_or_else(|| anyhow::anyhow!("all retries exhausted")))
    }

    pub async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GenerateResponse> {
        let result = self
            .generate_with_retry(self.primary.as_ref(), &self.primary_provider, req)
            .await;

        match result {
            Ok(resp) => Ok(resp),
            Err(primary_err) => {
                if let Some(ref fallback) = self.fallback {
                    tracing::warn!(
                        primary_provider = %self.primary_provider,
                        fallback_provider = %self.fallback_provider,
                        error = %primary_err,
                        "Primary provider failed, falling back"
                    );

                    GEN_AI_FALLBACK_COUNT.add(1, &[]);

                    let fallback_req = GenerateRequest {
                        model: self.fallback_model.clone(),
                        ..req.clone()
                    };

                    self.generate_with_retry(
                        fallback.as_ref(),
                        &self.fallback_provider,
                        &fallback_req,
                    )
                    .await
                } else {
                    Err(anyhow::anyhow!(
                        "primary provider {} failed after retries: {}",
                        self.primary_provider,
                        primary_err
                    ))
                }
            }
        }
    }
}

fn truncate(s: &str, max: usize) -> String {
    if s.len() <= max {
        s.to_string()
    } else {
        s.char_indices()
            .take_while(|&(i, _)| i < max)
            .map(|(_, c)| c)
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_truncate_short() {
        assert_eq!(truncate("hello", 10), "hello");
    }

    #[test]
    fn test_truncate_exact() {
        assert_eq!(truncate("hello", 5), "hello");
    }

    #[test]
    fn test_truncate_long() {
        let result = truncate("hello world", 5);
        assert_eq!(result, "hello");
    }

    #[test]
    fn test_truncate_multibyte_safe() {
        let result = truncate("hé世界!", 3);
        assert!(result.len() <= 3);
        assert!(result.is_char_boundary(result.len()));
    }
}
