from typing import Callable, Dict, Any
from lang.interpreter import FlowLang
from studio.stdplgns.sss.enumerator import from_reduced_rank_index, test_for_all
from studio.stdplgns.sss.classifier import classify_system


def run_sessie_enumeration(
        workflow_config: dict,
        on_progress: Callable[[float], None],
        on_log: Callable[[str], None],
        on_result: Callable[[int, str, str, int, str], None],
        is_cancelled: Callable[[], bool]
) -> None:
    """
    Executes the Sessie enumeration batch defined by the .sss YAML file.
    """
    search = workflow_config.get('search_space', {})
    start_idx = search.get('start_index', 1)
    end_idx = search.get('end_index', 100)

    sim = workflow_config.get('simulation', {})
    max_steps = sim.get('max_steps', 200)
    init_state = sim.get('initial_state', 'A')
    halt_on_inert = sim.get('halt_on_inert', True)

    total_runs = end_idx - start_idx + 1
    current_idx = start_idx

    while current_idx <= end_idx:
        if is_cancelled():
            on_log("[bold orange]Execution cancelled by user.[/]")
            break

        # 1. Generate & Filter
        rs_data = from_reduced_rank_index(current_idx)

        # Use test_for_all to check the 9 jump conditions
        jump_target = test_for_all(rs_data)

        if jump_target is not None:
            current_idx = jump_target
            continue

        # 2. Compile FlowLang Code
        flow_code = f'@init("{init_state}");\n'
        rules_str_list = []
        for match, replace in rs_data["RuleSet"]:
            m_str = match if match else '""'
            r_str = replace if replace else '""'
            flow_code += f"{m_str} -> {r_str};\n"
            rules_str_list.append(f"{m_str}->{r_str}")

        rules_display = ", ".join(rules_str_list)

        # 3. Evolve
        try:
            flow = FlowLang()
            flow.interpret(flow_code)
            flow.evolve(max_steps, break_when_inert=halt_on_inert)

            # 4. Classify
            metrics = classify_system(flow, max_steps)

            # 5. Report Result
            on_result(
                current_idx,
                rs_data["QCode"],
                rules_display,
                metrics["actual_steps"],
                metrics["classification"]
            )

        except Exception as e:
            on_log(f"[red]Simulation Error at Index {current_idx}: {e}[/red]")

        # Update Progress
        progress_pct = ((current_idx - start_idx) / total_runs) * 100
        on_progress(progress_pct)

        current_idx += 1

    on_progress(100.0)
    on_log("[bold green]Sessie Pipeline Complete![/]")
