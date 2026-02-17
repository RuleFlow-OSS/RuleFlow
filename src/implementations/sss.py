"""Sequential Substitution System"""
from typing import Sequence, cast
from copy import deepcopy, copy
from core.engine import (
    Flow,
    SpaceState1D as SpaceState,
    Cell,
    Rule as RuleABC,
    RuleMatch,
    RuleSet,
    DeltaSpace
)


class ReplacementRule(RuleABC):
    def __init__(self, rule_str: str):
        RuleABC.__init__(self)
        selector, op, target = rule_str.split(' ')
        self.selector_cells = tuple(Cell(c) for c in selector.strip())
        self.target_cells = tuple(Cell(c) for c in target.strip())
        self.group_break = True  # set flags to modify the RuleSet behavior

    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        output = ()
        if matches:=next(spaces[0].find(self.selector_cells), None):
            output += (RuleMatch(space=spaces[0], matches=(matches,), conflicts=set()),)
        return output

    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        selector: tuple[int, int] = rule_matches[0].matches[0]
        old_space: SpaceState = cast(SpaceState, rule_matches[0].space)  # we cast to satisfy the type checker
        new_space: SpaceState = copy(old_space)
        cell_deltas = new_space.substitute(selector, deepcopy(self.target_cells))
        return (DeltaSpace(old_space, (new_space,), (cell_deltas,)),)


class SSS(Flow):
    def __init__(self, rule_set: list[str], initial_space: str):
        super().__init__()
        self.set_initial_space([SpaceState([Cell(s) for s in initial_space])])
        self.set_ruleset(RuleSet([ReplacementRule(s) for s in rule_set]))


if __name__ == "__main__":
    sss = SSS(["ABA -> AAB", "A -> ABA"], "AB")
    sss.evolve_n(20)
    print(sss)
    # from core.graph import CausalGraph
    # g = CausalGraph(sss)
    # g.save_to_gephi_file('./graph.gexf')
