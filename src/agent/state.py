from datetime import datetime
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from .models import Step

InputMode = Literal["text", "camera", "gallery", "voice", "pdf"]


class CompletionSignals(TypedDict):
    """Behavioral inputs that feed the done-detector."""

    idle_seconds: int
    rapid_skip_count: int
    helpful_taps: int
    explicit_done: bool
    explicit_stuck: bool


def empty_signals() -> CompletionSignals:
    return CompletionSignals(
        idle_seconds=0,
        rapid_skip_count=0,
        helpful_taps=0,
        explicit_done=False,
        explicit_stuck=False,
    )


class HomeworkState(TypedDict, total=False):
    # ── Session metadata ───────────────────────
    session_id: str
    student_id: str
    started_at: datetime

    # ── Input ──────────────────────────────────
    input_mode: InputMode
    raw_input: str

    # ── Parsed ─────────────────────────────────
    extracted_text: str
    detected_subject: str
    detected_class_level: int

    # ── Breakdown ──────────────────────────────
    steps: list[Step]
    current_step_index: int

    # ── Conversation ───────────────────────────
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Done detection ─────────────────────────
    last_interaction_at: datetime
    completion_signals: CompletionSignals

    # ── Output ─────────────────────────────────
    is_complete: bool
    saved_to_library: bool

    # ── Errors ─────────────────────────────────
    last_error: str
    retry_count: int
