pub mod anthropic;
pub mod client;
pub mod openai;
pub mod pricing;

pub use client::LlmClient;

#[derive(Debug, Clone)]
pub struct GenerateRequest {
    pub model: String,
    pub system: String,
    pub prompt: String,
    pub temperature: f32,
    pub max_tokens: u32,
    pub stage: String,
}

#[derive(Debug, Clone)]
pub struct GenerateResponse {
    pub content: String,
    pub model: String,
    pub input_tokens: u32,
    pub output_tokens: u32,
    pub cost_usd: f64,
    pub finish_reason: String,
    pub provider: String,
}

#[async_trait::async_trait]
pub trait Provider: Send + Sync {
    async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GenerateResponse>;
    fn name(&self) -> &str;
}
