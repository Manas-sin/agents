"""JSON-file backed memory store — survives server restarts."""

import json
import threading
from collections.abc import Sequence
from pathlib import Path

from ..interfaces import MemoryStore
from ..models import Message, Role


class FileStore(MemoryStore):
    """Persists messages to a single JSON file. Fine for single-process dev;
    swap to Honcho/Postgres for multi-worker production."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._sessions: dict[str, list[Message]] = self._read()

    def _read(self) -> dict[str, list[Message]]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {
            sid: [Message(role=Role(m["role"]), content=m["content"]) for m in msgs]
            for sid, msgs in raw.items()
        }

    def _write(self) -> None:
        serializable = {
            sid: [{"role": m.role.value, "content": m.content} for m in msgs]
            for sid, msgs in self._sessions.items()
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(serializable, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._path)

    def load(self, session_id: str) -> Sequence[Message]:
        with self._lock:
            return list(self._sessions.get(session_id, []))

    def save(self, session_id: str, message: Message) -> None:
        with self._lock:
            self._sessions.setdefault(session_id, []).append(message)
            self._write()
