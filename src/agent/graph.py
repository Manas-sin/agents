"""Homework agent graph: classify → breakdown → present → solve loop → confirm → save."""

from functools import partial

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .config import Settings
from .done_detection import detect_done_state
from .nodes import (
    breakdown,
    classify,
    completion_prompt,
    present_breakdown,
    save_to_library,
    solve_step,
)
from .state import HomeworkState


def _route_after_solve(state: HomeworkState) -> str:
    decision = detect_done_state(state)
    if decision == "ask_done":
        return "completion_prompt"
    if decision == "offer_help":
        # MVP: keep solving. Real version routes to offer_different_help node.
        return "solve_step"
    if state["current_step_index"] >= len(state["steps"]):
        return "completion_prompt"
    return "solve_step"


def _route_after_confirm(state: HomeworkState) -> str:
    return "save_to_library" if state.get("is_complete") else "solve_step"


def build_homework_graph(settings: Settings):
    graph = StateGraph(HomeworkState)

    graph.add_node("classify", partial(classify, settings=settings))
    graph.add_node("breakdown", partial(breakdown, settings=settings))
    graph.add_node("present_breakdown", present_breakdown)
    graph.add_node("solve_step", partial(solve_step, settings=settings))
    graph.add_node("completion_prompt", completion_prompt)
    graph.add_node("save_to_library", save_to_library)

    graph.add_edge(START, "classify")
    graph.add_edge("classify", "breakdown")
    graph.add_edge("breakdown", "present_breakdown")
    graph.add_edge("present_breakdown", "solve_step")
    graph.add_conditional_edges(
        "solve_step",
        _route_after_solve,
        {"solve_step": "solve_step", "completion_prompt": "completion_prompt"},
    )
    graph.add_conditional_edges(
        "completion_prompt",
        _route_after_confirm,
        {"solve_step": "solve_step", "save_to_library": "save_to_library"},
    )
    graph.add_edge("save_to_library", END)

    checkpointer = InMemorySaver()
    return graph.compile(checkpointer=checkpointer)


def make_graph():
    return build_homework_graph(Settings())
