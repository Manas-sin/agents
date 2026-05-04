"""Graph nodes for the homework agent. Each node mutates HomeworkState."""

from datetime import datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.types import interrupt

from .config import Settings
from .llm.factory import get_chat_model
from .models import (
    BreakdownOutput,
    ClassificationOutput,
    Step,
)
from .persona import INFI_PERSONA
from .state import HomeworkState, empty_signals


# ─── 1. Classify ──────────────────────────────────────────────────────────────


def classify(state: HomeworkState, settings: Settings) -> dict:
    text = state["raw_input"]
    llm = get_chat_model("classification", settings).with_structured_output(
        ClassificationOutput
    )
    result: ClassificationOutput = llm.invoke(
        [
            SystemMessage(content="You classify K12 homework. Respond strictly in the schema."),
            HumanMessage(content=f"Homework:\n{text}"),
        ]
    )
    return {
        "extracted_text": text,
        "detected_subject": result.subject.value,
        "detected_class_level": result.class_level,
    }


# ─── 2. Breakdown ─────────────────────────────────────────────────────────────


_BREAKDOWN_INSTRUCTIONS = """\
Break the homework into ordered steps. Each step is ONE logical sub-question
(not one line of working). Number them in source order unless reordering is
clearly better pedagogically.
"""


def breakdown(state: HomeworkState, settings: Settings) -> dict:
    llm = get_chat_model("breakdown", settings).with_structured_output(BreakdownOutput)
    output: BreakdownOutput = llm.invoke(
        [
            SystemMessage(content=INFI_PERSONA),
            SystemMessage(content=_BREAKDOWN_INSTRUCTIONS),
            HumanMessage(
                content=(
                    f"Subject: {state.get('detected_subject', 'unknown')}\n"
                    f"Class level: {state.get('detected_class_level', 'unknown')}\n\n"
                    f"Homework:\n{state['extracted_text']}"
                )
            ),
        ]
    )
    steps = [
        Step(
            id=f"step_{i + 1}",
            question=draft.question,
            subject=draft.subject,
            difficulty=draft.difficulty,
        )
        for i, draft in enumerate(output.steps)
    ]
    return {"steps": steps, "current_step_index": 0}


# ─── 3. Present breakdown (INTERRUPT) ─────────────────────────────────────────


def present_breakdown(state: HomeworkState) -> dict:
    response = interrupt(
        {
            "type": "breakdown_review",
            "message": "Ye plan banaya hai. Order theek hai? Ya badalna hai?",
            "steps": [s.model_dump(mode="json") for s in state["steps"]],
        }
    )
    if response.get("action") == "reorder":
        new_order: list[str] = response["step_ids"]
        by_id = {s.id: s for s in state["steps"]}
        reordered = [by_id[sid] for sid in new_order if sid in by_id]
        return {"steps": reordered, "current_step_index": 0}
    return {"current_step_index": 0}


# ─── 4. Step solver (INTERRUPT loop) ──────────────────────────────────────────


def solve_step(state: HomeworkState, settings: Settings) -> dict:
    idx = state["current_step_index"]
    steps = list(state["steps"])
    step = steps[idx]

    if step.status == "pending":
        step.status = "in_progress"
        step.started_at = datetime.utcnow()
        intro = _intro_for_step(step, settings)
        intro_msg = AIMessage(content=intro)
    else:
        intro_msg = None

    last_reply = None
    if intro_msg is None:
        for prev in reversed(state.get("messages") or []):
            if isinstance(prev, AIMessage):
                last_reply = prev.content if isinstance(prev.content, str) else str(prev.content)
                break

    response = interrupt(
        {
            "type": "step_chat",
            "step": step.model_dump(mode="json"),
            "intro": intro_msg.content if intro_msg else None,
            "last_reply": last_reply,
        }
    )

    action = response.get("action", "ask")
    student_text = response.get("text", "")
    new_messages: list = []

    match action:
        case "done":
            step.status = "completed"
            step.completed_at = datetime.utcnow()
            steps[idx] = step
            return {
                "steps": steps,
                "current_step_index": idx + 1,
                "messages": _wrap_msgs(intro_msg, student_text, "Bahut badhiya. Next step pe chalte hain."),
                "completion_signals": _signals_after(state, action),
                "last_interaction_at": datetime.utcnow(),
            }
        case "skip":
            step.status = "skipped"
            steps[idx] = step
            return {
                "steps": steps,
                "current_step_index": idx + 1,
                "messages": _wrap_msgs(intro_msg, student_text, "Theek hai, skip kar dete hain."),
                "completion_signals": _signals_after(state, action),
                "last_interaction_at": datetime.utcnow(),
            }
        case "hint":
            step.hints_used += 1
            steps[idx] = step
            reply = _reply_in_step(step, student_text or "Mujhe hint do.", settings, hint=True)
            return {
                "steps": steps,
                "current_step_index": idx,
                "messages": _wrap_msgs(intro_msg, student_text or "[hint requested]", reply),
                "completion_signals": _signals_after(state, action),
                "last_interaction_at": datetime.utcnow(),
            }
        case _:  # "ask" / free chat
            reply = _reply_in_step(step, student_text, settings)
            return {
                "steps": steps,
                "current_step_index": idx,
                "messages": _wrap_msgs(intro_msg, student_text, reply),
                "completion_signals": _signals_after(state, action),
                "last_interaction_at": datetime.utcnow(),
            }


def _intro_for_step(step: Step, settings: Settings) -> str:
    llm = get_chat_model("step_solver", settings)
    response = llm.invoke(
        [
            SystemMessage(content=INFI_PERSONA),
            HumanMessage(
                content=(
                    f"Introduce this step in 1-2 lines. Don't solve it yet, just frame it.\n\n"
                    f"Step: {step.question}\n"
                    f"Subject: {step.subject}\n"
                    f"Difficulty: {step.difficulty}"
                )
            ),
        ]
    )
    return _content_str(response)


def _reply_in_step(step: Step, student_text: str, settings: Settings, hint: bool = False) -> str:
    llm = get_chat_model("step_solver", settings)
    instruction = (
        "Give the student a hint — point them in the right direction without solving."
        if hint
        else "Respond to the student about this specific step."
    )
    response = llm.invoke(
        [
            SystemMessage(content=INFI_PERSONA),
            SystemMessage(
                content=(
                    f"Current step: {step.question}\nSubject: {step.subject}\n\n"
                    f"{instruction}"
                )
            ),
            HumanMessage(content=student_text or "(no message)"),
        ]
    )
    return _content_str(response)


def _content_str(response) -> str:
    return response.content if isinstance(response.content, str) else str(response.content)


def _wrap_msgs(intro: AIMessage | None, student_text: str, reply: str) -> list:
    msgs: list = []
    if intro is not None:
        msgs.append(intro)
    if student_text:
        msgs.append(HumanMessage(content=student_text))
    msgs.append(AIMessage(content=reply))
    return msgs


def _signals_after(state: HomeworkState, action: str) -> dict:
    sig = dict(state.get("completion_signals") or empty_signals())
    if action == "skip":
        sig["rapid_skip_count"] = sig.get("rapid_skip_count", 0) + 1
    else:
        sig["rapid_skip_count"] = 0
    if action in {"hint"}:
        sig["helpful_taps"] = sig.get("helpful_taps", 0) + 1
    sig["explicit_done"] = action == "explicit_done"
    sig["explicit_stuck"] = action == "explicit_stuck"
    sig["idle_seconds"] = 0
    return sig


# ─── 5. Completion prompt (INTERRUPT) ─────────────────────────────────────────


def completion_prompt(state: HomeworkState) -> dict:
    completed = sum(1 for s in state["steps"] if s.status == "completed")
    response = interrupt(
        {
            "type": "completion_check",
            "message": f"Lagta hai ho gaya? {completed} steps khatam.",
            "options": ["Haan, done", "Nahi, thoda baaki"],
        }
    )
    return {"is_complete": bool(response.get("confirmed"))}


# ─── 6. Library saver ─────────────────────────────────────────────────────────


def save_to_library(state: HomeworkState) -> dict:
    # TODO: write to real DB and to Honcho. For MVP we just mark done.
    return {"saved_to_library": True}
