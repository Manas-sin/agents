from .interfaces import LLM, MemoryStore
from .models import Message, Role


class ChatService:
    """One chat turn: load history, ask the LLM, save both messages."""

    def __init__(self, llm: LLM, memory: MemoryStore) -> None:
        self._llm = llm
        self._memory = memory

    def chat(self, session_id: str, user_input: str) -> Message:
        user_message = Message(role=Role.USER, content=user_input)

        history = list(self._memory.load(session_id))
        history.append(user_message)

        reply = self._llm.invoke(history)

        self._memory.save(session_id, user_message)
        self._memory.save(session_id, reply)
        return reply
