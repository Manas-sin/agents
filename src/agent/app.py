"""Wires all the pieces together — the only place that knows about every layer."""

from dataclasses import dataclass

from .chat_service import ChatService
from .config import Settings, get_settings
from .homework_service import HomeworkService
from .interfaces import LLM, MemoryStore
from .llm.factory import create_llm
from .memory.factory import create_memory


@dataclass(frozen=True, slots=True)
class App:
    settings: Settings
    llm: LLM
    memory: MemoryStore
    chat: ChatService
    homework: HomeworkService


def create_app(settings: Settings | None = None) -> App:
    settings = settings or get_settings()
    llm = create_llm(settings)
    memory = create_memory(settings)
    return App(
        settings=settings,
        llm=llm,
        memory=memory,
        chat=ChatService(llm=llm, memory=memory),
        homework=HomeworkService(settings=settings),
    )
