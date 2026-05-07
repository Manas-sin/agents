from pathlib import Path

from ..config import Settings
from ..interfaces import MemoryStore
from .file_store import FileStore


def create_memory(settings: Settings) -> MemoryStore:
    if settings.honcho_api_key:
        from .honcho import HonchoStore

        return HonchoStore(
            api_key=settings.honcho_api_key,
            app_name=settings.honcho_app_name,
        )
    return FileStore(Path(settings.memory_file_path))
