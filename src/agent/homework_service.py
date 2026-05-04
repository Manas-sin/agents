"""High-level facade over the homework graph. The API layer talks to this."""

from datetime import datetime
from typing import Any
from uuid import uuid4

from langgraph.types import Command

from .config import Settings
from .graph import build_homework_graph
from .state import HomeworkState, empty_signals


class HomeworkService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._graph = build_homework_graph(settings)

    def start(self, student_id: str, homework_text: str) -> dict[str, Any]:
        session_id = str(uuid4())
        initial: HomeworkState = {
            "session_id": session_id,
            "student_id": student_id,
            "started_at": datetime.utcnow(),
            "input_mode": "text",
            "raw_input": homework_text,
            "completion_signals": empty_signals(),
            "last_interaction_at": datetime.utcnow(),
            "is_complete": False,
            "saved_to_library": False,
            "retry_count": 0,
        }
        config = {"configurable": {"thread_id": session_id}}
        result = self._graph.invoke(initial, config=config)
        return self._envelope(session_id, result)

    def resume(self, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        result = self._graph.invoke(Command(resume=payload), config=config)
        return self._envelope(session_id, result)

    def get_state(self, session_id: str) -> dict[str, Any]:
        config = {"configurable": {"thread_id": session_id}}
        snapshot = self._graph.get_state(config)
        return self._envelope(session_id, snapshot.values, snapshot)

    def _envelope(self, session_id: str, values: dict, snapshot=None) -> dict[str, Any]:
        interrupt_payload = None
        if snapshot is None:
            try:
                snapshot = self._graph.get_state({"configurable": {"thread_id": session_id}})
            except Exception:
                snapshot = None

        if snapshot is not None and snapshot.tasks:
            for task in snapshot.tasks:
                if task.interrupts:
                    interrupt_payload = task.interrupts[0].value
                    break

        steps = values.get("steps") or []
        return {
            "session_id": session_id,
            "interrupt": interrupt_payload,
            "is_complete": values.get("is_complete", False),
            "saved_to_library": values.get("saved_to_library", False),
            "current_step_index": values.get("current_step_index", 0),
            "steps": [s.model_dump(mode="json") for s in steps],
            "detected_subject": values.get("detected_subject"),
            "detected_class_level": values.get("detected_class_level"),
        }
