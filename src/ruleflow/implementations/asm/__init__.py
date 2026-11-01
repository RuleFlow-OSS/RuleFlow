"""
MIPS32 causal tracing, extensible Rich renderables for CPU state,
and multi-instruction `MipsInstructionRule` execution in RuleFlow.
"""
from ruleflow.implementations.asm.prettier import *
from ruleflow.implementations.asm.model import (
    MipsRuleSet, MipsInstructionRule,
    MipsInstruction, MipsSpace, MipsTopology
)


if __name__ == "__main__":
    init_data = """
.data
    array:  .word 45, 12, 89, 7, 23, 10
    length: .word 6
    sum_result: .word 0
    max_result: .word 0
"""
    list_analysis = init_data + """
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
    bubble_sort = init_data + """
.text
main:
    la   $t0, array          # base address
    la   $t1, length
    lw   $t1, 0($t1)         # n = 6
    addiu $t1, $t1, -1       # n - 1
    li   $t2, 0              # i = 0

outer_b:
    beq  $t2, $t1, done_b
    li   $t3, 0              # j = 0
    subu $t4, $t1, $t2       # limit = n - 1 - i
    move $t5, $t0            # ptr = &array[0]

inner_b:
    beq  $t3, $t4, next_outer_b
    lw   $t6, 0($t5)         # a = array[j]
    lw   $t7, 4($t5)         # b = array[j+1]
    slt  $t8, $t7, $t6       # if b < a
    beqz $t8, no_swap_b
    sw   $t7, 0($t5)         # array[j] = b
    sw   $t6, 4($t5)         # array[j+1] = a

no_swap_b:
    addiu $t5, $t5, 4
    addiu $t3, $t3, 1
    j    inner_b

next_outer_b:
    addiu $t2, $t2, 1
    j    outer_b

done_b:
    nop
"""
    selection_sort = init_data + """
.text
main:
    la   $t0, array          # base address
    la   $t1, length
    lw   $t1, 0($t1)         # n = 6
    addiu $t9, $t1, -1       # n - 1
    li   $t2, 0              # i = 0

outer_s:
    beq  $t2, $t9, done_s
    move $t3, $t2            # min_idx = i
    sll  $t4, $t2, 2
    addu $t4, $t0, $t4       # &array[i]
    lw   $t5, 0($t4)         # min_val = array[i]
    addiu $t6, $t2, 1        # j = i + 1

inner_s:
    beq  $t6, $t1, swap_s
    sll  $t7, $t6, 2
    addu $t7, $t0, $t7       # &array[j]
    lw   $t8, 0($t7)         # val = array[j]
    slt  $s0, $t8, $t5       # val < min_val?
    beqz $s0, next_inner_s
    move $t3, $t6            # min_idx = j
    move $t5, $t8            # min_val = val

next_inner_s:
    addiu $t6, $t6, 1
    j    inner_s

swap_s:
    beq  $t3, $t2, next_outer_s
    sll  $t7, $t3, 2
    addu $t7, $t0, $t7       # &array[min_idx]
    lw   $t8, 0($t4)         # temp = array[i]
    sw   $t5, 0($t4)         # array[i] = min_val
    sw   $t8, 0($t7)         # array[min_idx] = temp

next_outer_s:
    addiu $t2, $t2, 1
    j    outer_s

done_s:
    nop
"""

    from rich.console import Console
    console = Console(width=150, soft_wrap=True)
    import ruleflow.core.engine as ce
    import ruleflow.implementations.asm.assembler as u
    from ruleflow.implementations.asm.prettier import (
        print_bundle_summary,
        print_causal_trace,
        print_full_hardware_state,
    )
    def new_flow(src: str):
        bundle = u.parse_and_load_mips(
            src,
            track_reads_as_causal=True,
            track_pc_as_cell=True,
            steps_per_rule='basic_block'
        )
        print_bundle_summary(bundle, console)
        flow = ce.Flow()
        flow.set_ruleset(bundle.ruleset)
        flow.set_initial_space((bundle.initial_space,))
        return flow, bundle

    # First Flow
    f1, b1 = new_flow(bubble_sort)
    f1.evolve(n_steps=200, halt_on_inert=True)
    print_causal_trace(f1, b1, console=console)
    print_full_hardware_state(b1, console=console)

    # Second Flow
    # f2, b2 = new_flow(selection_sort)
    # f2.evolve(n_steps=200, halt_on_inert=True)
    # print_causal_trace(f2, b2, console=console)
    # print_full_hardware_state(b2, console=console)

    # Causal Graphs
    # from ruleflow.analysis.causal_graph import EventCausalityGraph, compute_ged_similarity
    # g1: EventCausalityGraph = EventCausalityGraph().build_from_flow(
    #     f1, slice(0, len(f1.events)), collapse_multi_edges=False
    # )
    # g2: EventCausalityGraph = EventCausalityGraph().build_from_flow(
    #     f2, slice(0, len(f2.events)), collapse_multi_edges=False
    # )
    # print(compute_ged_similarity(g1, g2, approx_steps=2))

    # Edge Different Set List
    # def extract_str_from_edsl(g: list[list[int]]):
    #     return ''.join([''.join(str(i) for i in dl) if dl else '-' for dl in g])
    # print(extract_str_from_edsl(g1.build_edsl()))

    # Graph Vis
    # from pyvis.network import Network
    # net = Network(directed=True)
    # net.from_nx(g1)
    # net.write_html("temp_vis_js.html", open_browser=True)
