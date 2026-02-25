use async_openai::{
    Client,
    config::OpenAIConfig,
    types::chat::{
        ChatCompletionRequestMessage, ChatCompletionRequestSystemMessage,
        ChatCompletionRequestSystemMessageContent, ChatCompletionRequestUserMessage,
        ChatCompletionRequestUserMessageContent, CreateChatCompletionRequest,
    },
};

use super::{GenerateRequest, GenerateResponse, Provider};

pub struct OpenAIProvider {
    client: Client<OpenAIConfig>,
    provider_name: String,
}

impl OpenAIProvider {
    pub fn new(api_key: &str) -> Self {
        let config = OpenAIConfig::new().with_api_key(api_key);
        Self {
            client: Client::with_config(config),
            provider_name: "openai".to_string(),
        }
    }

    pub fn new_google(api_key: &str) -> Self {
        let config = OpenAIConfig::new()
            .with_api_key(api_key)
            .with_api_base("https://generativelanguage.googleapis.com/v1beta/openai");
        Self {
            client: Client::with_config(config),
            provider_name: "google".to_string(),
        }
    }

    pub fn new_ollama(base_url: &str) -> Self {
        let config = OpenAIConfig::new()
            .with_api_key("ollama")
            .with_api_base(format!("{base_url}/v1"));
        Self {
            client: Client::with_config(config),
            provider_name: "ollama".to_string(),
        }
    }
}

#[async_trait::async_trait]
impl Provider for OpenAIProvider {
    async fn generate(&self, req: &GenerateRequest) -> anyhow::Result<GenerateResponse> {
        let messages = vec![
            ChatCompletionRequestMessage::System(ChatCompletionRequestSystemMessage {
                content: ChatCompletionRequestSystemMessageContent::Text(req.system.clone()),
                name: None,
            }),
            ChatCompletionRequestMessage::User(ChatCompletionRequestUserMessage {
                content: ChatCompletionRequestUserMessageContent::Text(req.prompt.clone()),
                name: None,
            }),
        ];

        #[allow(deprecated)]
        let request = CreateChatCompletionRequest {
            model: req.model.clone(),
            messages,
            temperature: Some(req.temperature),
            max_completion_tokens: Some(req.max_tokens),
            ..Default::default()
        };

        let response = self.client.chat().create(request).await?;

        let content = response
            .choices
            .first()
            .and_then(|c| c.message.content.clone())
            .unwrap_or_default();

        let finish_reason = response
            .choices
            .first()
            .and_then(|c| c.finish_reason)
            .map(|r| format!("{r:?}").to_lowercase())
            .unwrap_or_default();

        let (input_tokens, output_tokens) = match &response.usage {
            Some(usage) => (usage.prompt_tokens, usage.completion_tokens),
            None => (0, 0),
        };

        Ok(GenerateResponse {
            content,
            model: response.model,
            input_tokens,
            output_tokens,
            cost_usd: 0.0,
            finish_reason,
            provider: String::new(),
        })
    }

    fn name(&self) -> &str {
        &self.provider_name
    }
}
