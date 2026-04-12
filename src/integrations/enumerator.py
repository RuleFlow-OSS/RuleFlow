"""
This code currently contains rudimentary enumeration decoder tools for rulesets. Later we will want to
generalize this into framework of tools for this type of tooling.
"""
import math


def base_converter():
    pass


def sss_decoder(charset: str, index: int) -> list[tuple[str, str]]:
    """
    Generates the Sequential Substitution System (SSS) ruleset for a given index
    using the Reduced Sessie Enumeration (RSS) algorithm described in the
    'An Improved Generalized Enumeration of Substitution Systems' paper.

    The RSS algorithm provides a bijective mapping between positive integers
    and SSS rulesets. It uses a base-5 (quinary) encoding to construct rulesets
    by iteratively modifying a base state.

    Args:
        charset: A string of characters to use for the rules (e.g. "AB").
                 'A' corresponds to weight 1, 'B' to weight 2, etc.
        index: The enumeration index (0-based).

    Returns:
        A list of tuples, where each tuple contains (pattern, replacement).
    """
    if index < 0:
        raise ValueError("Index must be non-negative.")

    # The algorithm in the paper uses 1-based indexing.
    i = index + 1

    # Calculate 'n', which relates to the weight of the ruleset.
    # Formula derived from: i_min(n) = (5^n + 3) / 4 + 1
    # n = floor(log_5(4*i - 3))
    # Note: 4*i - 3 is always >= 1 for i >= 1
    n = math.floor(math.log(4 * i - 3, 5))

    # Calculate 'j', the offset within the weight class.
    # j = i - offset
    j = i - (5**n + 3) // 4  # within the "block"

    # Convert 'j' to quinary (base-5) digits, padded to length 'n'.
    quinary_digits = []
    temp_j = j
    for _ in range(n):
        quinary_digits.append(temp_j % 5)
        temp_j //= 5
    quinary_digits.reverse()

    # RSS Construction
    # The enumeration starts with a base ruleset containing a single string "A".
    ans = [[1]]
    for digit in quinary_digits:
        if digit == 0:
            # End string, insert two empty strings, start new string "A"
            # Operation: Append {}, {}, {1}
            ans.extend([[], [], [1]])
        elif digit == 1:
            # End string, insert one empty string, start new string "A"
            # Operation: Append {}, {1}
            ans.extend([[], [1]])
        elif digit == 2:
            # End string, start new string "A"
            # Operation: Append {1}
            ans.append([1])
        elif digit == 3:
            # End character, start new character "A"
            # Operation: Append 1 to the last string
            ans[-1].append(1)
        elif digit == 4:
            # Increment last character
            # Operation: Increment the last weight in the last string
            if not ans or not ans[-1]:
                ans.append([1])
            ans[-1][-1] += 1
    max_weight = 0
    for s_weights in ans:
        if s_weights:
            max_weight = max(max_weight, max(s_weights))
    if max_weight > len(charset):
        raise ValueError(f"Index {index} requires a charset of at least {max_weight} characters "
                         f"(generated max weight {max_weight}, but charset length is {len(charset)}).")
    strings = []
    for s_weights in ans:
        s = "".join(charset[ w -1] for w in s_weights)
        strings.append(s)
    if len(strings) % 2 != 0:
        strings.append("")
    rules = []
    for k in range(0, len(strings), 2):
        rules.append((strings[k], strings[k +1]))
    return rules


def wolfram_numbering_scheme(charset: str, index: int) -> list[tuple[str, str]]:
    """
    Generates Wolfram Elementary Cellular Automata rules for a given index.

    Args:
        charset: A string of two characters (e.g. "01" or "AB").
                 charset[0] is '0' (dead), charset[1] is '1' (alive).
        index: The Wolfram rule number (0-255).
    """
    if len(charset) != 2:
        raise ValueError("Charset must contain exactly 2 characters.")
    binary_patterns: list[tuple[int, int, int]] = [
        (1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0),
        (0, 1, 1), (0, 1, 0), (0, 0, 1), (0, 0, 0)
    ]
    rule_bits = f'{index:08b}'  # Convert index to 8-bit binary string (e.g., 30 -> '00011110')
    rules = []
    for (b1, b2, b3), result_bit in zip(binary_patterns, rule_bits):
        selector = f"{charset[b1]}{charset[b2]}{charset[b3]}"
        replacement = charset[int(result_bit)]
        rules.append((selector, replacement))
    return rules


if __name__ == '__main__':
    # Example usage based on paper examples
    # print("Wolfram Rule 30 (AB):")
    # print(wolfram_numbering_scheme('AB', 30))

    # print("\nSSS RSS Index 0 (Paper Index 1):")
    # print(sss_enumeration('AB', 0))
    print(sss_decoder('AB', 8239))
