"""Sequential Substitution System"""
from typing import Sequence, cast
from core.engine import (
    Flow,
    Cell,
    Rule as RuleABC,
    RuleMatch,
    RuleSet,
    DeltaSpace
)
from core.topologies.nd_space import SpaceState1D as SpaceState
from core.topologies.finder import VectorRegexSearch
from core.graph import EventCausalityGraph
import numpy as np
finder: VectorRegexSearch = VectorRegexSearch()


class ReplacementRule(RuleABC):
    def __init__(self, rule_str: str):
        super().__init__()
        selector, _, target = rule_str.split(' ')
        self.selector = np.frombuffer(selector.encode(), dtype=np.uint8)
        self.target = np.frombuffer(target.encode(), dtype=np.uint8)
        self.group_break = True  # set flags to modify the RuleSet behavior

    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        output = ()
        if matches := next(finder(self.selector, spaces[0].vec.data.logical_data), None):
            output += (RuleMatch(space=spaces[0], matches=(matches.span(),), conflicts=set()),)
        return output

    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        selector: tuple[int, int] = rule_matches[0].matches[0]
        old_space: SpaceState = cast(SpaceState, rule_matches[0].space)  # we cast to satisfy the type checker
        new_space: SpaceState = old_space.next_gen()
        cell_deltas = new_space.substitute(selector, self.target)
        return (DeltaSpace(old_space, (new_space,), (cell_deltas,)),)


class SSS(Flow):
    def __init__(self, rule_set: list[str], initial_space: str):
        super().__init__()
        self.set_initial_space([SpaceState(np.frombuffer(initial_space.encode(), dtype=np.uint8))])
        self.set_ruleset(RuleSet([ReplacementRule(s) for s in rule_set]))


if __name__ == "__main__":
    sss = SSS(["ABA -> AAB", "A -> ABA"], "AB")
    sss.evolve(20)
    g = EventCausalityGraph()
    g.build(sss, (0, 15, 1))
    from pyvis.network import Network
    net = Network()
    net.from_nx(g)
    net.write_html('causal_graph.html', open_browser=True)

    # a = np.frombuffer("ABC".encode(), dtype=np.uint8)
    # print(a)

    # from core.graph import CausalGraph
    # g = CausalGraph(sss)
    # g.save_to_gephi_file('./graph.gexf')
