from typing import Callable, Any
from lang.interpreter import FlowLang
from core.topologies.tooling.rff_encoding import chr_rff
from studio.stdplgns.sss._system_classifier import classify_system
import studio.stdplgns.sss._ruleset_tests as tests


def run_sessie_enumeration(
        workflow_config: dict,
        on_progress: Callable[[float], None],
        on_result: Callable[[int, str, str, int, str, str], None],
        is_cancelled: Callable[[], bool],
        on_log: Callable[[str], None] | Any
) -> None:
    # ================ Read Config ================
    # Search Space
    search = workflow_config.get('search_space', {})
    start_idx = search.get('start_index', 1)
    end_idx = search.get('end_index', 100)

    # Simulation
    sim = workflow_config.get('simulation', {})
    raw_init = sim.get('initial_state', 'A')

    # Convert input string to ordinals dynamically
    if isinstance(raw_init, str):
        init_state = "".join(raw_init)
    else:
        init_state = "".join(chr_rff(c) for c in raw_init)

    max_steps = sim.get('max_steps', 200)

    filter_names = workflow_config.get('filters', [])
    filter_funcs = [getattr(tests, f"test_for_{f}") for f in filter_names if hasattr(tests, f"test_for_{f}")]

    total_runs = max(1, end_idx - start_idx + 1)
    current_idx = start_idx

    # ================ Execute Pipeline ================
    while current_idx <= end_idx:
        if is_cancelled():
            on_log("[bold orange]Execution cancelled by user.[/]")
            break

        rs_data = tests.from_reduced_rank_index(current_idx)
        jumped = False

        # Apply Declarative Filters
        for func, name in zip(filter_funcs, filter_names):
            target_idx = func(rs_data)
            if target_idx is not None:
                rules_display = ", ".join(
                    [f"{''.join(chr_rff(c + 65) for c in m)} -> {''.join(chr_rff(c + 65) for c in r)}" for m, r in rs_data["RuleSet"]])
                on_result(current_idx, rs_data["QCode"], rules_display, 0, "Filtered", f"Skipped by {name}")
                current_idx = target_idx
                jumped = True
                break

        if jumped:
            continue

        # Simulate via FlowLang Generation
        flow_code = f'@init("{init_state}");\n'
        for match, replace in rs_data["RuleSet"]:
            m_str: str = str(match)
            r_str: str = str(replace)

            if not m_str and not r_str:
                continue
            elif not m_str:
                flow_code += f"[0] > {r_str};\n"
            elif not r_str:
                flow_code += f"{m_str} >< ;\n"
            else:
                flow_code += f"{m_str} -> {r_str};\n"

        try:
            flow = FlowLang()
            flow.interpret(flow_code)
            flow.evolve(max_steps)

            cls_data = classify_system(flow, max_steps)
            rules_display = ", ".join(
                [f"{''.join(chr_rff(c) for c in m)}->{''.join(chr_rff(c) for c in r)}" for m, r in rs_data["RuleSet"]])
            on_result(current_idx, rs_data["QCode"], rules_display, flow.current_event_idx, cls_data["classification"],
                      "Simulated")
        except Exception as e:
            on_log(f"[bold red]Simulation Error at Index {current_idx}:[/] {e}")

        current_idx += 1
        on_progress(min(((current_idx - start_idx) / total_runs) * 100, 100))

    if not is_cancelled():
        on_log("[bold green]Sessie Pipeline Complete![/]")
        on_progress(100.0)
