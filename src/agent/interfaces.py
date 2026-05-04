from abc import ABC, abstractmethod
from collections.abc import Sequence

from .models import Message


class LLM(ABC):
    """Anything that can take a list of messages and return one reply."""

    @abstractmethod
    def invoke(self, messages: Sequence[Message]) -> Message:
        ...


class MemoryStore(ABC):
    """Anything that can remember messages per session."""

    @abstractmethod
    def load(self, session_id: str) -> Sequence[Message]:
        ...

    @abstractmethod
    def save(self, session_id: str, message: Message) -> None:
        ...
