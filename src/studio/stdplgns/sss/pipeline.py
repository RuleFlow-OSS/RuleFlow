from typing import Callable, Dict, Any
from lang.interpreter import FlowLang

# Import ALL the math functions and tests
from studio.stdplgns.sss.enumerator import (
    from_reduced_rank_index,
    test_for_conflicting_rules,
    test_for_identity_rule,
    test_for_non_solo_identity_rule,
    test_for_renamed_ruleset,
    test_for_initial_substring_rule,
    test_for_non_solo_initial_substring_rule,
    test_for_shortening_ruleset,
    test_for_unbalanced_ruleset,
    test_for_all
)
from studio.stdplgns.sss.classifier import classify_system


class SessieContext:
    """The API exposed to the user's YAML exec blocks."""

    def __init__(self, index: int, rs_data: dict, init_state: str):
        self.index: int = index
        self.rs_data: dict = rs_data
        self.qcode: str = rs_data.get('QCode', '')
        self.ruleset: list = rs_data.get('RuleSet', [])

        self.next_index: int = index + 1
        self.skip: bool = False
        self.tags: set = set()
        self.flow: FlowLang | None = None
        self.init_state: str = init_state
        self.steps_run: int = 0

    def jump(self, target_index: int) -> None:
        """Instructs the pipeline to skip the remainder of the pipeline and jump to a new index."""
        self.next_index = target_index
        self.skip = True

    def evolve(self, max_steps: int = 200, halt_on_inert: bool = True) -> None:
        """Opt-in method to computationally evolve the system."""
        flow_code = f'@init("{self.init_state}");\n'
        for match, replace in self.ruleset:
            m_str = match if match else ''
            r_str = replace if replace else ''
            flow_code += f"{m_str} -> {r_str};\n"

        flow = FlowLang()
        flow.interpret(flow_code)
        flow.evolve(max_steps, break_when_inert=halt_on_inert)
        self.flow = flow
        self.steps_run = flow.current_event_idx


def run_sessie_enumeration(
        workflow_config: dict,
        on_progress: Callable[[float], None],
        on_log: Callable[[str], None],
        on_result: Callable[[int, str, str, int, str], None],
        is_cancelled: Callable[[], bool]
) -> None:
    search = workflow_config.get('search_space', {})
    start_idx = search.get('start_index', 1)
    end_idx = search.get('end_index', 100)

    sim = workflow_config.get('simulation', {})
    init_state = sim.get('initial_state', 'A')

    pipeline_steps = workflow_config.get('pipeline', [])
    total_runs = end_idx - start_idx + 1
    current_idx = start_idx

    # The environment exposed to the exec() blocks: ALL tests are now available
    global_env = {
        'test_for_conflicting_rules': test_for_conflicting_rules,
        'test_for_identity_rule': test_for_identity_rule,
        'test_for_non_solo_identity_rule': test_for_non_solo_identity_rule,
        'test_for_renamed_ruleset': test_for_renamed_ruleset,
        'test_for_initial_substring_rule': test_for_initial_substring_rule,
        'test_for_non_solo_initial_substring_rule': test_for_non_solo_initial_substring_rule,
        'test_for_shortening_ruleset': test_for_shortening_ruleset,
        'test_for_unbalanced_ruleset': test_for_unbalanced_ruleset,
        'test_for_all': test_for_all,
        'classify_system': classify_system
    }

    while current_idx <= end_idx:
        if is_cancelled():
            on_log("[bold orange]Execution cancelled by user.[/]")
            break

        # Generate base math
        rs_data = from_reduced_rank_index(current_idx)
        ctx = SessieContext(current_idx, rs_data, init_state)
        local_env = {'ctx': ctx}

        # Dynamically execute user pipeline
        for step in pipeline_steps:
            if ctx.skip:
                break

            code = step.get('exec', '')
            if code:
                try:
                    exec(code, global_env, local_env)
                except Exception as e:
                    on_log(f"[red]Pipeline Exec Error at Index {current_idx}: {e}[/red]")
                    ctx.skip = True

        # Only report if the user didn't tell the context to skip
        if not ctx.skip:
            rules_display = ", ".join([f"{m if m else '\"\"'}->{r if r else '\"\"'}" for m, r in ctx.ruleset])
            tags_str = ", ".join(ctx.tags) if ctx.tags else "Analyzed"
            on_result(current_idx, ctx.qcode, rules_display, ctx.steps_run, tags_str)

        current_idx = ctx.next_index

        progress_pct = min(((current_idx - start_idx) / total_runs) * 100, 100)
        on_progress(progress_pct)

    on_progress(100.0)
    on_log("[bold green]Sessie Pipeline Complete![/]")
