"""Pure scoring function — no I/O, no LLM, fully unit-testable."""

from typing import Literal

from .state import CompletionSignals, HomeworkState

Decision = Literal["continue", "ask_done", "offer_help"]


def detect_done_state(state: HomeworkState) -> Decision:
    signals = state.get("completion_signals") or _empty()
    steps = state.get("steps", [])
    total = len(steps)
    completed = sum(1 for s in steps if s.status == "completed")

    if signals["explicit_done"]:
        return "ask_done"

    if signals["explicit_stuck"]:
        return "offer_help"

    if signals["rapid_skip_count"] >= 3:
        return "offer_help"

    if total > 0:
        ratio = completed / total
        if signals["idle_seconds"] > 90 and ratio >= 0.7:
            return "ask_done"
        if signals["idle_seconds"] > 120 and ratio < 0.3:
            return "offer_help"

    if total > 0 and completed == total:
        return "ask_done"

    return "continue"


def _empty() -> CompletionSignals:
    return CompletionSignals(
        idle_seconds=0,
        rapid_skip_count=0,
        helpful_taps=0,
        explicit_done=False,
        explicit_stuck=False,
    )
