"""Sequential Substitution System"""
from typing import Sequence, cast
from core.engine import (
    Flow,
    Rule as RuleABC,
    RuleMatch,
    RuleSet,
    DeltaSpace,
    DeltaCell
)
from core.topologies.nd_space import SpaceState1D as SpaceState
from core.topologies.tooling.finder import VectorRegexSearch
import numpy as np
finder: VectorRegexSearch = VectorRegexSearch()


class ReplacementRule(RuleABC):
    def __init__(self, rule_str: str):
        super().__init__()
        selector, _, target = rule_str.split(' ')
        self.selector = finder.normalize_pattern(selector)
        self.target = np.frombuffer(target.encode(), dtype=np.uint8)

    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        if matches := next(finder(self.selector, spaces[0].vec.data.logical_data), None):
            return (RuleMatch(space=spaces[0], matches=(matches.span(),), conflicts=frozenset()),)
        return ()

    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        selector: tuple[int, int] = rule_matches[0].matches[0]
        old_space: SpaceState = cast(SpaceState, rule_matches[0].space)  # we cast to satisfy the type checker
        new_space: SpaceState = old_space.next_gen()
        cell_deltas: DeltaCell = new_space.substitute(selector, self.target)
        return (DeltaSpace(old_space, (new_space,), (cell_deltas,)),)


class SSS(Flow):
    def __init__(self, rule_set: list[str], initial_space: str):
        super().__init__()
        self.set_initial_space([SpaceState(np.frombuffer(initial_space.encode(), dtype=np.uint8))])
        self.set_ruleset(RuleSet([ReplacementRule(s) for s in rule_set]))


if __name__ == "__main__":
    # System
    system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space='AB')
    system.evolve(20)
    print(system.__str__())

    # Evolution Table
    from core.topologies.tooling.prettier import SpaceState1DFormatter
    from rich.console import Console
    formatter = SpaceState1DFormatter()
    formatter.show_symbols = True
    # formatter.highlight_cells_with_id = {6, 28}
    console = Console(width=1000)
    for event in system.events:
        console.print(formatter(event.spaces.__next__()))
        #console.print(formatter(next(event.spaces)))

    # Causal Graph
    # from core.graph import EventCausalityGraph
    # from pyvis.network import Network
    # g = EventCausalityGraph()
    # g.build(system, slice(0, 16))
    # net = Network(directed=True)
    # net.from_nx(g)
    # net.show('causal_graph.html', notebook=False)
