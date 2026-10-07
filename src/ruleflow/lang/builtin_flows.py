PRESETS: dict[str, str] = {
    '/lang/ca.preset': """
@self.regex_searcher.set_find_args(overlapped=True);
@self.literal_searcher.set_overlapping_mode(True);
@compress(0);
@merge(0);
-pl[inf] -mr[0,inf]
""",  # default import code to streamline the use of CAs in the 0th group.

    '/lang/global_multiway.preset': """
-gb[False]
-sr[0, inf]
-mr[0, inf]
-bl[inf]
""",  # search buffer becomes "corrupt" after edits, so disable.

    '/lang/ordered_multiway.preset': """
-gb[True]
-sr[0, inf]
-mr[0, inf]
-bl[inf]
""", # only the first rule (in ordered precedence) that matches is branched out
}

FLOWS: dict[str, str] = {
    # ==== Wolfram Numbering Scheme Ruleset Enumeration ====
    '/lang/eca.pflow': """
charset: str = args[0]
if len(charset) != 2:
    raise ValueError("Charset must contain exactly 2 characters.")
index: int = args[1]
binary_patterns: list[tuple[int, int, int]] = [
    (1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0),
    (0, 1, 1), (0, 1, 0), (0, 0, 1), (0, 0, 0)
]
for (b1, b2, b3), tb in zip(binary_patterns, f'{index:08b}'):
    ---
    {charset[b1]}{charset[b2]}{charset[b3]} --> .{charset[int(tb)]};
    ---
""",

    # ==== Totalistic Cellular Automata Enumeration ====  TODO: this needs a lot of testing...
    '/lang/tca.pflow': """
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
"""
}
