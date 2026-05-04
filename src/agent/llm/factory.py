from typing import Literal

from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from ..config import Settings
from ..interfaces import LLM
from .anthropic import AnthropicLLM
from .gemini import GeminiLLM
from .openai import OpenAILLM

Task = Literal["classification", "breakdown", "step_solver", "vision", "default"]


# Task → (provider, model) routing. The provider here is overridden by
# settings.llm_provider when set — this is just the per-task model preference
# for whichever provider is active.
LLM_ROUTING: dict[Task, tuple[str, str]] = {
    "classification": ("anthropic", "claude-haiku-4-5"),
    "breakdown": ("anthropic", "claude-sonnet-4-6"),
    "step_solver": ("anthropic", "claude-sonnet-4-6"),
    "vision": ("anthropic", "claude-sonnet-4-6"),
    "default": ("anthropic", "claude-sonnet-4-6"),
}


GEMINI_MODELS_BY_TASK: dict[Task, str] = {
    "classification": "gemini-2.5-flash-lite",
    "breakdown": "gemini-2.5-flash-lite",
    "step_solver": "gemini-2.5-flash-lite",
    "vision": "gemini-2.5-flash-lite",
    "default": "gemini-2.5-flash-lite",
}


def create_llm(settings: Settings) -> LLM:
    """Default chat LLM (used by simple chat path)."""
    if settings.llm_provider == "fake":
        from .fake import FakeLLM
        return FakeLLM()
    if settings.llm_provider == "anthropic":
        return AnthropicLLM(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.anthropic_api_key,
        )
    if settings.llm_provider == "gemini":
        return GeminiLLM(
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            api_key=settings.google_api_key,
        )
    return OpenAILLM(
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        api_key=settings.openai_api_key,
    )


def get_chat_model(task: Task, settings: Settings):
    """Return a raw LangChain chat model for graph nodes (supports
    structured output, streaming, vision — features the LLM interface hides)."""
    if settings.llm_provider == "fake":
        from .fake import FakeChatModel
        return FakeChatModel()

    if settings.llm_provider == "gemini":
        model = GEMINI_MODELS_BY_TASK.get(task, GEMINI_MODELS_BY_TASK["default"])
        kwargs: dict = {"model": model, "temperature": settings.llm_temperature}
        if settings.google_api_key:
            kwargs["google_api_key"] = settings.google_api_key
        return ChatGoogleGenerativeAI(**kwargs)

    provider, model = LLM_ROUTING.get(task, LLM_ROUTING["default"])
    if provider == "anthropic":
        kwargs = {"model": model, "temperature": settings.llm_temperature}
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key
        return ChatAnthropic(**kwargs)
    kwargs = {"model": model, "temperature": settings.llm_temperature}
    if settings.openai_api_key:
        kwargs["api_key"] = settings.openai_api_key
    return ChatOpenAI(**kwargs)
