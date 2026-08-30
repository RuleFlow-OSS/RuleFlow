import math
from typing import TypedDict, Optional


class RuleSetData(TypedDict):
    Index: int
    QCode: str
    RuleSet: list[tuple[tuple[int, ...], tuple[int, ...]]]
    Weight: int


def rule_weight(ruleset: list[tuple[tuple[int, ...], tuple[int, ...]]]) -> int:
    """Calculates the total weight of a ruleset (0-based ordinals: A=0 -> weight 1, B=1 -> weight 2...)."""
    return sum(val + 1 for pair in ruleset for s in pair for val in s)


def from_reduced_rank_quinary_code(qcode: str) -> RuleSetData:
    """Converts a Base-5 Q-Code back to its Index and RuleSet using integer ordinals."""
    w = len(qcode) + 1
    index = int(qcode, 5) + (5 ** (w - 1) + 3) // 4 if qcode else 1

    ans = [[1]]
    for op_char in qcode:
        op = int(op_char)
        if op == 0:
            ans.extend([[], [], [1]])
        elif op == 1:
            ans.extend([[], [1]])
        elif op == 2:
            ans.append([1])
        elif op == 3:
            ans[-1].append(1)
        elif op == 4:
            ans[-1][-1] += 1

    # Convert weights to 0-based ordinals (e.g., weight 1 -> ordinal 0)
    strings = []
    for chars in ans:
        strings.append(tuple(c - 1 for c in chars if c > 0))

    if len(strings) % 2 != 0:
        strings.append(())

    ruleset = [(strings[k], strings[k + 1]) for k in range(0, len(strings), 2)]

    return {
        "Index": index,
        "QCode": qcode,
        "RuleSet": ruleset,
        "Weight": rule_weight(ruleset)
    }


def from_reduced_rank_index(index: int) -> RuleSetData:
    if index < 1: raise ValueError("Index must be >= 1")
    n = math.floor(round(math.log(4 * index - 3, 5), 10))
    j = index - (5 ** n + 3) // 4

    qcode = ""
    if n > 0:
        temp = j
        for _ in range(n):
            qcode = str(temp % 5) + qcode
            temp //= 5

    return from_reduced_rank_quinary_code(qcode)


def _drop_end(s: str, tail: int) -> str:
    return s[:-tail] if tail > 0 else s


def test_for_conflicting_rules(rs_data: RuleSetData) -> Optional[int]:
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    lhs = [r[0] for r in rs]
    max_len = len(lhs)

    for j in range(1, max_len - 1):
        if len(lhs[j]) == 0:
            tailweight = rule_weight(rs[j + 1:])
            if tailweight == 0: return index + 1
            newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
            return from_reduced_rank_quinary_code(newqcode)["Index"]

    for j in range(1, max_len):
        for i in range(j):
            l_i, l_j = lhs[i], lhs[j]
            if not l_i: continue
            for k in range(len(l_j) - len(l_i) + 1):
                if l_j[k:k + len(l_i)] == l_i:
                    matchend = k + len(l_i)
                    modified_rule = (l_j[matchend:], rs[j][1])
                    tailweight = rule_weight([modified_rule] + rs[j + 1:])
                    if tailweight == 0: return index + 1
                    newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
                    return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


def test_for_identity_rule(rs_data: RuleSetData) -> Optional[int]:
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    for rulenum, (l, r) in enumerate(rs):
        if l == r:
            tailweight = rule_weight(rs[rulenum + 1:])
            if tailweight == 0: return index + 1
            op_code = "1" if len(l) == 0 else "3"
            newqcode = _drop_end(qcode, tailweight) + op_code + "0" * (tailweight - 1)
            return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


def test_for_non_solo_identity_rule(rs_data: RuleSetData) -> Optional[int]:
    if len(rs_data["RuleSet"]) == 1: return None
    return test_for_identity_rule(rs_data)


def test_for_renamed_ruleset(rs_data: RuleSetData) -> Optional[int]:
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    rsn = []
    for l, r in rs:
        rsn.extend(l)
        rsn.extend(r)

    max_char = -1
    bad_pos = -1
    for i, val in enumerate(rsn):
        if val == max_char + 1:
            max_char += 1
        elif val > max_char + 1:
            bad_pos = i
            break

    if bad_pos == -1: return None

    tailweight = sum(v + 1 for v in rsn[bad_pos + 1:])
    newqcode = _drop_end(qcode, tailweight) + "4" * tailweight
    return from_reduced_rank_quinary_code(newqcode)["Index"] + 1


def test_for_initial_substring_rule(rs_data: RuleSetData) -> Optional[int]:
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    if len(rs) == 0: return None

    l, r = rs[0]
    if l:
        for k in range(len(r) - len(l) + 1):
            if r[k:k + len(l)] == l:
                duppos = k + len(l)
                tailweight = rule_weight([(r[duppos:], ())] + rs[1:])
                if tailweight == 0: return index + 1
                newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
                return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


def test_for_non_solo_initial_substring_rule(rs_data: RuleSetData) -> Optional[int]:
    if len(rs_data["RuleSet"]) == 1: return None
    return test_for_initial_substring_rule(rs_data)


def test_for_shortening_ruleset(rs_data: RuleSetData) -> Optional[int]:
    shortens, lengthens = False, False
    for l, r in rs_data["RuleSet"]:
        diff = len(l) - len(r)
        if diff > 0:
            shortens = True
        elif diff < 0:
            lengthens = True
    if shortens and not lengthens:
        return rs_data["Index"] + 1
    return None


def test_for_unbalanced_ruleset(rs_data: RuleSetData) -> Optional[int]:
    lhs_chars, rhs_chars = set(), set()
    for l, r in rs_data["RuleSet"]:
        lhs_chars.update(l)
        rhs_chars.update(r)
    if lhs_chars != rhs_chars:
        return rs_data["Index"] + 1
    return None
