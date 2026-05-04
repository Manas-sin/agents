from agent.done_detection import detect_done_state
from agent.models import Step
from agent.state import HomeworkState, empty_signals


def _state(steps=None, **signals):
    sig = empty_signals()
    sig.update(signals)
    return HomeworkState(steps=steps or [], current_step_index=0, completion_signals=sig)


def _step(status="pending"):
    return Step(id="s1", question="q", subject="math", difficulty="easy", status=status)


def test_explicit_done_asks_to_confirm():
    assert detect_done_state(_state(explicit_done=True)) == "ask_done"


def test_explicit_stuck_offers_help():
    assert detect_done_state(_state(explicit_stuck=True)) == "offer_help"


def test_three_skips_offers_help():
    assert detect_done_state(_state(rapid_skip_count=3)) == "offer_help"


def test_idle_with_most_done_asks_to_confirm():
    steps = [_step("completed")] * 8 + [_step("pending")] * 2
    assert detect_done_state(_state(steps, idle_seconds=120)) == "ask_done"


def test_idle_with_barely_started_offers_help():
    steps = [_step("completed")] + [_step("pending")] * 9
    assert detect_done_state(_state(steps, idle_seconds=200)) == "offer_help"


def test_all_completed_asks_to_confirm():
    steps = [_step("completed")] * 3
    assert detect_done_state(_state(steps)) == "ask_done"


def test_default_continues():
    steps = [_step("pending")] * 3
    assert detect_done_state(_state(steps)) == "continue"
