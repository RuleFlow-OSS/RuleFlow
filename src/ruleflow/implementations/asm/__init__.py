"""
End-to-end demonstration of MIPS32 causal tracing, extensible Rich renderables,
and multi-instruction `MipsInstructionRule` execution in RuleFlow.
"""
from ruleflow.implementations.asm.prettier import *
from ruleflow.implementations.asm.model import (
    MipsRuleSet, MipsInstructionRule,
    MipsInstruction, MipsSpace, MipsTopology
)


if __name__ == "__main__":
    sample_mips_program = """
    .data
        array:      .word 12, 45, 7, 89, 23
        length:     .word 5
        sum_result: .word 0
        max_result: .word 0

    .text
    main:
        la   $t0, array          # $t0 = base address of array
        la   $t1, length         # $t1 = address of length
        lw   $t1, 0($t1)         # $t1 = length (5)
        li   $t2, 0              # $t2 = loop index i = 0
        li   $t3, 0              # $t3 = running sum = 0
        lw   $t4, 0($t0)         # $t4 = running max = array[0]

    loop:
        beq  $t2, $t1, done      # if i == length, exit loop
        lw   $t5, 0($t0)         # $t5 = array[i]
        addu $t3, $t3, $t5       # sum += array[i]

        slt  $t6, $t4, $t5       # $t6 = 1 if max < array[i] else 0
        beqz $t6, skip_max       # if max >= array[i], skip updating max
        move $t4, $t5            # max = array[i]

    skip_max:
        addiu $t0, $t0, 4        # advance array pointer by 4 bytes
        addiu $t2, $t2, 1        # i += 1
        j     loop               # repeat loop

    done:
        la   $t7, sum_result     # $t7 = address of sum_result
        sw   $t3, 0($t7)         # memory[sum_result] = sum (176)
        la   $t7, max_result     # $t7 = address of max_result
        sw   $t4, 0($t7)         # memory[max_result] = max (89)
    """
#     sample_mips_program = """
# main:
#     addiu   $sp,$sp,-32
#     sw      $fp,28($sp)
#     move    $fp,$sp
#     li      $2,1
#     sw      $2,8($fp)
#     li      $2,2
#     sw      $2,12($fp)
#     li      $2,3
#     sw      $2,16($fp)
#     nop
#     move    $sp,$fp
#     lw      $fp,28($sp)
#     addiu   $sp,$sp,32
#     jr      $31
#     nop
# """

    from rich.console import Console
    import ruleflow.core.engine as ce
    import ruleflow.implementations.asm.assembler as u
    from ruleflow.implementations.asm.prettier import (
        print_bundle_summary,
        print_causal_trace,
        print_full_hardware_state,
    )
    console = Console(width=150, soft_wrap=True)
    bundle = u.parse_and_load_mips(
        sample_mips_program,
        track_reads_as_causal=True,
        track_pc_as_cell=False,
        steps_per_rule=1
    )
    print_bundle_summary(bundle, console)

    flow = ce.Flow()
    flow.set_ruleset(bundle.ruleset)
    flow.set_initial_space((bundle.initial_space,))
    flow.evolve(n_steps=50, halt_on_inert=True)

    print_causal_trace(flow, bundle, console=console)
    print_full_hardware_state(bundle, console=console)

    # import networkx as nx
    # from pyvis.network import Network
    # from ruleflow.analysis.causal_graph import EventCausalityGraph
    # g: nx.MultiDiGraph = EventCausalityGraph().build_from_flow(
    #     flow, slice(0, len(flow.events)), collapse_multi_edges=False
    # )
    # net = Network(directed=True)
    # net.from_nx(g)
    # net.write_html("temp_vis_js.html", open_browser=True)
