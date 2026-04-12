"""Provides all the tools for optimized and rigorous graph analysis.

FRAMEWORK NOTES:
- use pyvis Network to render interactive graphs.

TODO:
- Redesign to support live graph updating (to keep up to date with flow).
- Add more tools for seamless analysis and integrations.
"""
from core.engine import Flow
from networkx import MultiDiGraph
from typing import Sequence, Self


class EventCausalityGraph(MultiDiGraph):
    def build(self, flow: Flow,
                 event_range: tuple[int, int, int],
                 collapse_multi_edges: bool = False) -> Self:
        # construct causal graph - because each node is literally the time, and thus index, it can be used to query to the actual event for more granular information.
        connected_container: type[tuple] | type[set] = set if collapse_multi_edges else tuple
        for event in flow.events[event_range[0]:event_range[1]+1:event_range[2]]:
            causally_connected: Sequence[int] = connected_container(event.causally_connected_events)
            self.add_node(
                event.time,
                # these get passed on to the nodes of VisJS network.
                label=f'{event.time}',
                title=f' Causal Distance: {event.causal_distance_to_creation}\n'
                      f'Connected Events: {len(causally_connected)}',
                shape='box'
            )
            for parent_time in causally_connected:
                self.add_edge(parent_time, event.time)
        return self
