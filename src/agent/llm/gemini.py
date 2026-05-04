from collections.abc import Sequence

from langchain_google_genai import ChatGoogleGenerativeAI

from ..interfaces import LLM
from ..models import Message
from .converters import from_langchain, to_langchain


class GeminiLLM(LLM):
    def __init__(self, model: str, temperature: float, api_key: str | None = None) -> None:
        kwargs: dict = {"model": model, "temperature": temperature}
        if api_key:
            kwargs["google_api_key"] = api_key
        self._client = ChatGoogleGenerativeAI(**kwargs)

    def invoke(self, messages: Sequence[Message]) -> Message:
        response = self._client.invoke(to_langchain(messages))
        return from_langchain(response)
