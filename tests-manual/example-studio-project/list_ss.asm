.data
    array:  .word 45, 12, 89, 7, 23, 10
    length: .word 6

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