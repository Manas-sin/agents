from collections import defaultdict
from collections.abc import Sequence

from ..interfaces import MemoryStore
from ..models import Message


class InMemoryStore(MemoryStore):
    """Keeps messages in a Python dict — used for tests and local dev."""

    def __init__(self) -> None:
        self._sessions: dict[str, list[Message]] = defaultdict(list)

    def load(self, session_id: str) -> Sequence[Message]:
        return list(self._sessions[session_id])

    def save(self, session_id: str, message: Message) -> None:
        self._sessions[session_id].append(message)
