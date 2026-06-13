import math
from typing import TypedDict, List, Tuple, Optional


class RuleSetData(TypedDict):
    Index: int
    QCode: str
    RuleSet: List[Tuple[str, str]]
    Weight: int


def rule_weight(ruleset: List[Tuple[str, str]]) -> int:
    """Calculates the total weight of a ruleset (A=1, B=2, C=3...)."""
    return sum(ord(char) - 64 for pair in ruleset for s in pair for char in s)


def from_reduced_rank_quinary_code(qcode: str) -> RuleSetData:
    """Converts a Base-5 Q-Code back to its Index and RuleSet."""
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

    strings = []
    for chars in ans:
        strings.append("".join(chr(c + 64) for c in chars if c > 0))
    if len(strings) % 2 != 0:
        strings.append("")

    ruleset = [(strings[k], strings[k + 1]) for k in range(0, len(strings), 2)]
    return {
        "Index": index,
        "QCode": qcode,
        "RuleSet": ruleset,
        "Weight": rule_weight(ruleset)
    }


def from_reduced_rank_index(index: int) -> RuleSetData:
    """Converts a positive integer index into a Base-5 Q-Code and RuleSet Data."""
    if index < 1:
        raise ValueError("Index must be >= 1")

    n = math.floor(math.log(4 * index - 3, 5))
    j = index - (5 ** n + 3) // 4

    qcode = ""
    if n > 0:
        temp = j
        for _ in range(n):
            qcode = str(temp % 5) + qcode
            temp //= 5

    return from_reduced_rank_quinary_code(qcode)


def _drop_end(s: str, tail: int) -> str:
    """Helper to safely slice off the end of a string even if tail is 0."""
    return s[:-tail] if tail > 0 else s


# ==========================================
# TEST 1: TestForConflictingRules (Long Jump)
# ==========================================
def test_for_conflicting_rules(rs_data: RuleSetData) -> Optional[int]:
    """Preempted rules. Returns jump target if conflict is found."""
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    lhs = [r[0] for r in rs]
    max_len = len(lhs)

    # Check for non-final creation rules ("" -> something)
    for j in range(1, max_len - 1):
        if len(lhs[j]) == 0:
            tailweight = rule_weight(rs[j + 1:])
            if tailweight == 0: return index + 1
            newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
            return from_reduced_rank_quinary_code(newqcode)["Index"]

    # Check for prefix substring conflicts
    for j in range(1, max_len):
        for i in range(j):
            if lhs[i] in lhs[j]:
                matchend = lhs[j].find(lhs[i]) + len(lhs[i])
                modified_rule = (lhs[j][matchend:], rs[j][1])
                tailweight = rule_weight([modified_rule] + rs[j + 1:])
                if tailweight == 0: return index + 1
                newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
                return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


# ==========================================
# TEST 2: TestForIdentityRule (Long Jump)
# ==========================================
def test_for_identity_rule(rs_data: RuleSetData) -> Optional[int]:
    """Identity rules replace a string with itself."""
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    for rulenum, (l, r) in enumerate(rs):
        if l == r:
            tailweight = rule_weight(rs[rulenum + 1:])
            if tailweight == 0: return index + 1
            op_code = "1" if len(l) == 0 else "3"
            newqcode = _drop_end(qcode, tailweight) + op_code + "0" * (tailweight - 1)
            return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


# ==========================================
# TEST 3: TestForNonSoloIdentityRule (Long Jump)
# ==========================================
def test_for_non_solo_identity_rule(rs_data: RuleSetData) -> Optional[int]:
    if len(rs_data["RuleSet"]) == 1:
        return None
    return test_for_identity_rule(rs_data)


# ==========================================
# TEST 4: TestForRenamedRuleSet (Long Jump)
# ==========================================
def test_for_renamed_ruleset(rs_data: RuleSetData) -> Optional[int]:
    """Detects permutations of character labels (e.g. ABA vs BAB)."""
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    rsn = []
    for l, r in rs:
        rsn.extend([ord(c) - 64 for c in l])
        rsn.extend([ord(c) - 64 for c in r])

    max_char = 0
    bad_pos = -1
    for i, val in enumerate(rsn):
        if val == max_char + 1:
            max_char += 1
        elif val > max_char + 1:
            bad_pos = i
            break

    if bad_pos == -1: return None

    tailweight = sum(rsn[bad_pos + 1:])
    newqcode = _drop_end(qcode, tailweight) + "4" * tailweight
    return from_reduced_rank_quinary_code(newqcode)["Index"] + 1


# ==========================================
# TEST 5: TestForInitialSubstringRule (Long Jump)
# ==========================================
def test_for_initial_substring_rule(rs_data: RuleSetData) -> Optional[int]:
    rs, qcode, index = rs_data["RuleSet"], rs_data["QCode"], rs_data["Index"]
    if len(rs) == 0: return None

    l, r = rs[0]
    if l and l in r:
        duppos = r.find(l) + len(l)
        tailweight = rule_weight([(r[duppos:], "")] + rs[1:])
        if tailweight == 0: return index + 1
        newqcode = _drop_end(qcode, tailweight) + "4" + "0" * (tailweight - 1)
        return from_reduced_rank_quinary_code(newqcode)["Index"]
    return None


# ==========================================
# TEST 6: TestForNonSoloInitialSubstringRule (Long Jump)
# ==========================================
def test_for_non_solo_initial_substring_rule(rs_data: RuleSetData) -> Optional[int]:
    if len(rs_data["RuleSet"]) == 1:
        return None
    return test_for_initial_substring_rule(rs_data)


# ==========================================
# TEST 7: TestForShorteningRuleSet (No Long Jump)
# ==========================================
def test_for_shortening_ruleset(rs_data: RuleSetData) -> Optional[int]:
    """Returns index + 1 if the ruleset guarantees the state string will shrink and die out."""
    rs = rs_data["RuleSet"]
    shortens, lengthens = False, False
    for l, r in rs:
        diff = len(l) - len(r)
        if diff > 0:
            shortens = True
        elif diff < 0:
            lengthens = True

    if shortens and not lengthens:
        return rs_data["Index"] + 1
    return None


# ==========================================
# TEST 8: TestForUnbalancedRuleSet (No Long Jump)
# ==========================================
def test_for_unbalanced_ruleset(rs_data: RuleSetData) -> Optional[int]:
    """Returns index + 1 if characters appear only on one side of the rules."""
    rs = rs_data["RuleSet"]
    lhs_chars, rhs_chars = set(), set()
    for l, r in rs:
        lhs_chars.update(l)
        rhs_chars.update(r)

    if lhs_chars != rhs_chars:
        return rs_data["Index"] + 1
    return None


# ==========================================
# TEST 9: TestForAll (Aggregator)
# ==========================================
def test_for_all(rs_data: RuleSetData) -> Optional[int]:
    """Tries all tests in the optimal order for the longest possible jumps."""
    tests = [
        test_for_conflicting_rules,
        test_for_non_solo_identity_rule,
        test_for_renamed_ruleset,
        test_for_non_solo_initial_substring_rule,
        test_for_unbalanced_ruleset,
        test_for_shortening_ruleset
    ]
    for test in tests:
        jump = test(rs_data)
        if jump is not None:
            return jump
    return None
