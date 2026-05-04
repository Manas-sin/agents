from collections.abc import Sequence

from honcho import Honcho

from ..interfaces import MemoryStore
from ..models import Message, Role


class HonchoStore(MemoryStore):
    """Long-term memory backed by the Honcho service."""

    def __init__(self, api_key: str, app_name: str) -> None:
        self._client = Honcho(api_key=api_key)
        self._app_name = app_name

    def load(self, session_id: str) -> Sequence[Message]:
        peer = self._client.peer(session_id)
        history = peer.chat()
        return [
            Message(role=Role(turn.role), content=turn.content)
            for turn in getattr(history, "messages", [])
        ]

    def save(self, session_id: str, message: Message) -> None:
        peer = self._client.peer(session_id)
        peer.add_messages([{"role": message.role.value, "content": message.content}])
