PRESETS: dict[str, str] = {
    'ca.preset': """
@self.regex_searcher.set_find_args(overlapped=True)
@self.literal_searcher.set_overlapping_mode(True)
@compress(0);
@merge(0);
-pl[inf] -mr[0,inf]
""",  # default import code to streamline the use of CAs in the 0th group.

    'global_multiway.preset': """
-gb[false]
-sr[0, inf]
-mr[0, inf]
-bl[inf]
""",  # search buffer becomes "corrupt" after edits, so disable.

    'ordered_multiway.preset': """
-gb[true]
-sr[0, inf]
-mr[0, inf]
-bl[inf]
""", # only the first rule (in ordered precedence) that matches is branched out
}

FLOWS: dict[str, str] = {
    # ==== Wolfram Numbering Scheme Ruleset Enumeration ====
    'wns.static.pflow': """
charset: str = args[0]
if len(charset) != 2:
    raise ValueError("Charset must contain exactly 2 characters.")
index: int = args[1]
binary_patterns: list[tuple[int, int, int]] = [
    (1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0),
    (0, 1, 1), (0, 1, 0), (0, 0, 1), (0, 0, 0)
]
rule_bits = f'{index:08b}'  # Convert index to 8-bit binary string (e.g., 30 -> '00011110')
for (b1, b2, b3), result_bit in zip(binary_patterns, rule_bits):
    ---
    {charset[b1]}{charset[b2]}{charset[b3]} --> _{charset[int(result_bit)]};
    ---
""",

    # ==== Totalistic Cellular Automata Enumeration ====  NOTE: this needs a lot of testing...
    'tca.static.pflow': """
import itertools

charset: str = args[0]
index: int = args[1]
# Default to a 3-cell neighborhood (radius 1) if not explicitly provided
neighborhood_size: int = args[2] if len(args) > 2 else 3

if neighborhood_size % 2 == 0:
    raise ValueError("Neighborhood size must be odd to have a true center cell.")

k: int = len(charset)
max_sum = neighborhood_size * (k - 1)
num_sums = max_sum + 1

# Optional validation
if index < 0 or index >= (k ** num_sums):
    raise ValueError(f"For {k} colors and size {neighborhood_size}, index must be between 0 and {(k**num_sums)-1}")

rule_digits = []
temp_idx = index
for _ in range(num_sums):
    rule_digits.append(temp_idx % k)
    temp_idx //= k
rule_digits.reverse()

sum_to_target = { (max_sum - s): charset[rule_digits[s]] for s in range(num_sums) }

# Calculate how many `_` we need to skip the left side of the neighborhood
left_padding = "_" * (neighborhood_size // 2)

for p in itertools.product(range(k), repeat=neighborhood_size):
    pattern_sum = sum(p)
    target_char = sum_to_target[pattern_sum]

    # Reconstruct the string from the permutation
    pattern_str = "".join(charset[weight] for weight in p)

    ---
    {pattern_str} --> {left_padding}{target_char};
    ---
""",

    # TODO: all Sessie code should be removed to dedicated files.
    # ==== Reduced Sessie Enumeration ====
    # Generates the Sequential Substitution System (SSS) ruleset for a given index
    # using the Reduced Sessie Enumeration (RSS) algorithm described in the
    # 'An Improved Generalized Enumeration of Substitution Systems' paper.
    #
    # The RSS algorithm provides a bijective mapping between positive integers
    # and SSS rulesets. It uses a base-5 (quinary) encoding to construct rulesets
    # by iteratively modifying a base state.
    'rss.pflow': """
import math
charset: str = args[0]
index: int = args[1]
if index < 0:
    raise ValueError("Index must be non-negative.")

# The algorithm uses 1-based indexing
i = index + 1

# Calculate 'n' and 'j' based on the quinary mapping
n = math.floor(math.log(4 * i - 3, 5))
j = i - (5**n + 3) // 4

# Extract base-5 digits
quinary_digits = []
temp_j = j
for _ in range(n):
    quinary_digits.append(temp_j % 5)
    temp_j //= 5
quinary_digits.reverse()

# RSS Construction
ans = [[1]]
for digit in quinary_digits:
    if digit == 0:
        ans.extend([[], [], [1]])
    elif digit == 1:
        ans.extend([[], [1]])
    elif digit == 2:
        ans.append([1])
    elif digit == 3:
        ans[-1].append(1)
    elif digit == 4:
        if not ans or not ans[-1]:
            ans.append([1])
        ans[-1][-1] += 1
max_weight = max((max(s) for s in ans if s), default=0)
if max_weight > len(charset):
    raise ValueError(f"Index {index} requires a charset of at least {max_weight} characters.")
strings = []
for s_weights in ans:
    s = "".join(charset[w - 1] for w in s_weights)
    strings.append(s)
if len(strings) % 2 != 0:
    strings.append("")
for k in range(0, len(strings), 2):
    ---
    {strings[k]} -> {strings[k + 1]};
    ---
"""
}
