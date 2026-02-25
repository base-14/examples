use reqwest::header::{CONTENT_TYPE, HeaderMap, HeaderValue};
use serde::{Deserialize, Serialize};

use super::{GenerateRequest, GenerateResponse, Provider};

pub struct AnthropicProvider {
    client: reqwest::Client,
    api_key: String,
}

impl AnthropicProvider {
    pub fn new(api_key: &str) -> Self {
        Self {
            client: reqwest::Client::new(),
            api_key: api_key.to_string(),
        }
    }
}

#[derive(Serialize)]
struct AnthropicRequest {
    model: String,
    max_tokens: u32,
    system: String,
    messages: Vec<AnthropicMessage>,
}

#[derive(Serialize)]
struct AnthropicMessage {
    role: String,
    content: String,
}

#[derive(Deserialize)]
struct AnthropicResponse {
    content: Vec<AnthropicContent>,
    model: String,
    usage: AnthropicUsage,
    stop_reason: Option<String>,
}

#[derive(Deserialize)]
struct AnthropicContent {
    #[serde(rename = "type")]
    content_type: String,
    text: Option<String>,
}

#[derive(Deserialize)]
struct AnthropicUsage {
    input_tokens: u32,
    output_tokens: u32,
}

#[derive(Deserialize)]
struct AnthropicError {
    error: AnthropicErrorDetail,
}

#[derive(Deserialize)]
struct AnthropicErrorDetail {
    message: String,
}

#[async_trait::async_trait]
impl Provider for AnthropicProvider {
    async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GenerateResponse> {
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-api-key",
            HeaderValue::from_str(&self.api_key)
                .map_err(|e| anyhow::anyhow!("invalid API key header: {e}"))?,
        );
        headers.insert("anthropic-version", HeaderValue::from_static("2023-06-01"));
        headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));

        let body = AnthropicRequest {
            model: req.model.clone(),
            max_tokens: req.max_tokens,
            system: req.system.clone(),
            messages: vec![AnthropicMessage {
                role: "user".to_string(),
                content: req.prompt.clone(),
            }],
        };

        let response = self
            .client
            .post("https://api.anthropic.com/v1/messages")
            .headers(headers)
            .json(&body)
            .send()
            .await?;

        let status = response.status();
        if !status.is_success() {
            let error_body = response.text().await.unwrap_or_default();
            if let Ok(err) = serde_json::from_str::<AnthropicError>(&error_body) {
                return Err(anyhow::anyhow!(
                    "Anthropic API error ({}): {}",
                    status,
                    err.error.message
                ));
            }
            return Err(anyhow::anyhow!(
                "Anthropic API error ({}): {}",
                status,
                error_body
            ));
        }

        let resp: AnthropicResponse = response.json().await?;

        let content = resp
            .content
            .iter()
            .filter(|c| c.content_type == "text")
            .filter_map(|c| c.text.as_deref())
            .collect::<Vec<_>>()
            .join("");

        Ok(GenerateResponse {
            content,
            model: resp.model,
            input_tokens: resp.usage.input_tokens,
            output_tokens: resp.usage.output_tokens,
            cost_usd: 0.0,
            finish_reason: resp.stop_reason.unwrap_or_default(),
            provider: String::new(),
        })
    }

    fn name(&self) -> &str {
        "anthropic"
    }
}
