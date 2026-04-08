"""Provider-agnostic LLM factory.

Returns a langchain BaseChatModel so every downstream node works
regardless of which LLM backend is configured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
else:
    BaseChatModel = Any

from research_agent.config import settings


def create_llm(
    provider: str | None = None,
    model: str | None = None,
    **kwargs,
) -> BaseChatModel:
    """Instantiate a chat model for the configured (or specified) provider."""
    provider = provider or settings.llm_provider
    model_name = model or settings.resolved_llm_model(provider)

    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=settings.google_api_key,
            **kwargs,
        )

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            **kwargs,
        )

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            **kwargs,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. "
        "Supported: gemini, openai, anthropic"
    )


def with_structured_output(
    llm: BaseChatModel,
    schema: Any,
    *,
    provider: str | None = None,
) -> Any:
    """Apply provider-aware structured output settings."""
    resolved_provider = provider or settings.llm_provider
    if resolved_provider == "openai":
        return llm.with_structured_output(schema, method="function_calling")
    return llm.with_structured_output(schema)
