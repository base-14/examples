"""Provider-agnostic LangChain chat-model factory."""

from langchain_core.language_models import BaseChatModel

from runbook_assistant.config import get_settings


def build_chat_model() -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=s.llm_model,
            temperature=s.default_temperature,
            base_url=s.ollama_base_url,
            reasoning=s.ollama_reasoning,
        )
    if s.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=s.llm_model,
            temperature=s.default_temperature,
            max_tokens=s.default_max_tokens,
            api_key=s.anthropic_api_key,
        )
    if s.llm_provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=s.llm_model,
            temperature=s.default_temperature,
            api_key=s.openai_api_key,
        )
    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model=s.llm_model,
        temperature=s.default_temperature,
        google_api_key=s.google_api_key,
    )
