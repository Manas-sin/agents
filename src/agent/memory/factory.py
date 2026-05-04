from ..config import Settings
from ..interfaces import MemoryStore
from .in_memory import InMemoryStore


def create_memory(settings: Settings) -> MemoryStore:
    if settings.honcho_api_key:
        from .honcho import HonchoStore

        return HonchoStore(
            api_key=settings.honcho_api_key,
            app_name=settings.honcho_app_name,
        )
    return InMemoryStore()
