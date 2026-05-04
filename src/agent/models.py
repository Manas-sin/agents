from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Role(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class Subject(str, Enum):
    MATH = "math"
    SCIENCE = "science"
    ENGLISH = "english"
    HINDI = "hindi"
    SOCIAL = "social"
    OTHER = "other"


Difficulty = Literal["easy", "medium", "hard"]
StepStatus = Literal["pending", "in_progress", "completed", "skipped"]


class Message(BaseModel):
    role: Role
    content: str


class Step(BaseModel):
    id: str
    question: str
    subject: str
    difficulty: Difficulty
    status: StepStatus = "pending"
    student_answer: str | None = None
    hints_used: int = 0
    started_at: datetime | None = None
    completed_at: datetime | None = None


class StepDraft(BaseModel):
    """LLM output schema for one step in the breakdown."""

    question: str
    subject: str
    difficulty: Difficulty
    estimated_minutes: int = Field(ge=1, le=60)


class BreakdownOutput(BaseModel):
    """LLM output schema for the whole breakdown."""

    steps: list[StepDraft]
    estimated_total_minutes: int = Field(ge=1, le=240)


class ClassificationOutput(BaseModel):
    """LLM output for the cheap subject/level classifier."""

    subject: Subject
    class_level: int = Field(ge=1, le=12)
    overall_difficulty: Difficulty
