"""Offline demo LLM — returns canned responses so the agent runs without API keys.

Drop-in for ChatAnthropic / ChatOpenAI. Supports `.invoke()` and
`.with_structured_output(Schema)` — enough for every node to work end-to-end.
"""

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel

from ..interfaces import LLM
from ..models import (
    BreakdownOutput,
    ClassificationOutput,
    Message,
    Role,
    StepDraft,
    Subject,
)


class FakeLLM(LLM):
    """Conforms to the agent's LLM interface — used for the simple chat path."""

    def invoke(self, messages: Sequence[Message]) -> Message:
        return Message(role=Role.ASSISTANT, content="(demo mode) I'm a fake LLM. Set LLM_PROVIDER=anthropic for real responses.")


_HINTS = [
    "Hint: pehle constants ko ek side le aao, fir variable solve karo.",
    "Hint: formula yaad karo — area = 0.5 × base × height.",
    "Hint: chhote steps mein todo, ek baar mein sab karne ki zaroorat nahi.",
]


class FakeChatModel:
    """Stand-in for a real LangChain chat model. Returns scripted text."""

    _hint_index = 0

    def invoke(self, messages: Any, **_: Any) -> AIMessage:
        prompt_blob = " ".join(_content(m) for m in messages)

        if "Introduce this step" in prompt_blob:
            return AIMessage(
                content="Chal yeh step dekhte hain — ek baar question padh ke socho kya pucha hai. Try karo!"
            )
        if "Give the student a hint" in prompt_blob:
            FakeChatModel._hint_index = (FakeChatModel._hint_index + 1) % len(_HINTS)
            return AIMessage(content=_HINTS[FakeChatModel._hint_index])
        return AIMessage(
            content="Achha sawaal! Step-by-step sochte hain — pehle kya karna hai? Try karo, mai yahan hu."
        )

    def with_structured_output(self, schema: type[BaseModel]) -> "_FakeStructured":
        return _FakeStructured(schema)


class _FakeStructured:
    def __init__(self, schema: type[BaseModel]) -> None:
        self._schema = schema

    def invoke(self, messages: Any, **_: Any) -> BaseModel:
        if self._schema is ClassificationOutput:
            return ClassificationOutput(
                subject=Subject.MATH,
                class_level=7,
                overall_difficulty="medium",
            )
        if self._schema is BreakdownOutput:
            return BreakdownOutput(
                steps=_canned_breakdown_for(messages),
                estimated_total_minutes=10,
            )
        return self._schema()  # type: ignore[call-arg]


def _content(m: Any) -> str:
    c = getattr(m, "content", None)
    if isinstance(c, str):
        return c
    if isinstance(m, tuple) and len(m) == 2:
        return str(m[1])
    return str(m)


def _canned_breakdown_for(messages: Any) -> list[StepDraft]:
    """Build a 3-step plan based on lines in the homework text."""
    import re

    text = ""
    for m in messages:
        if isinstance(m, tuple):
            continue
        content = getattr(m, "content", None)
        if isinstance(content, str) and "Homework:" in content:
            text = content.split("Homework:", 1)[1]
            break

    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    lines = [re.sub(r"^\s*[-•\d]+[).]?\s*", "", ln).strip() for ln in raw_lines]
    lines = [ln for ln in lines if ln]
    if not lines:
        lines = ["Solve the first question", "Solve the next question", "Review your answers"]

    steps: list[StepDraft] = []
    for i, line in enumerate(lines[:5]):
        difficulty = "easy" if i == 0 else "medium" if i == 1 else "hard"
        steps.append(
            StepDraft(
                question=line[:200],
                subject="math",
                difficulty=difficulty,
                estimated_minutes=3,
            )
        )
    return steps
