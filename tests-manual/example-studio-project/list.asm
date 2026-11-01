.data
    array:  .word 45, 12, 89, 7, 23, 10
    length: .word 6
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
