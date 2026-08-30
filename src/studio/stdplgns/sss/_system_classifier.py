from lang.interpreter import FlowLang
from typing import Dict, Any


def classify_system(flow: FlowLang, requested_steps: int) -> Dict[str, Any]:
    halted = flow.current_event.inert
    actual_steps = flow.current_event_idx

    space_lengths = []
    for event in flow.events:
        first_space = next(event.spaces, None)
        if first_space is not None:
            space_lengths.append(len(first_space.vec))

    max_len = max(space_lengths) if space_lengths else 0
    final_len = space_lengths[-1] if space_lengths else 0

    if halted:
        classification = "Class 1 (Halted)"
    elif final_len > 1.5 * requested_steps:
        classification = "Class 3 (Chaotic/Rapid)"
    elif max_len == final_len and max_len < 50:
        classification = "Class 2 (Periodic/Bounded)"
    else:
        classification = "Class 4 (Complex)"

    return {
        "classification": classification,
        "halted": halted,
        "actual_steps": actual_steps,
        "max_length": max_len,
        "final_length": final_len
    }
