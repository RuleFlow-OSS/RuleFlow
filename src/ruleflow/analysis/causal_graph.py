"""Provides all the tools for optimized and rigorous graph analysis.

FRAMEWORK NOTES:
- use pyvis Network to render interactive graphs.

TODO:
- Redesign to support live graph updating (to keep up to date with flow).
- Add more tools for seamless analysis and integrations.
"""
from ruleflow.core.engine import Flow
from networkx import MultiDiGraph
import networkx as nx
from typing import Sequence, Self


class EventCausalityGraph(MultiDiGraph):
    def build_from_flow(self, flow: Flow,
                        event_range: slice,
                        collapse_multi_edges: bool = False) -> Self:
        # construct causal graph - because each node is literally the time, and thus index, it can be used to query to the actual event for more granular information.
        connected_container: type[tuple] | type[set] = set if collapse_multi_edges else tuple
        for event in flow.events[event_range]:
            causally_connected: Sequence[int] | set[int] = connected_container(event.causally_connected_events)
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

    def build_keyed_edsl(self) -> dict[int, list[int]]:
        keyed_edsl: dict[int, list[int]] = {}
        for edge in self.edges:
            if not keyed_edsl.get(edge[0]):
                keyed_edsl[edge[0]] = [edge[1] - edge[0]]
                continue
            keyed_edsl[edge[0]].append(edge[1] - edge[0])
        return keyed_edsl

    def build_edsl(self) -> list[list[int]]:
        keyed_edsl = self.build_keyed_edsl()
        edsl: list[list[int]] = []
        start_idx, end_idx = min(keyed_edsl.keys()), max(keyed_edsl.keys())
        for idx in range(start_idx, end_idx + 1):
            try:
                edsl.append(keyed_edsl[idx])
            except KeyError:
                edsl.append([])
        return edsl


def compute_ged_similarity(
    g1: nx.Graph,
    g2: nx.Graph,
    ged: float | None = None,
    approx_steps: int = 1
) -> dict[str, float]:
    """Computes normalized similarity scores in [0.0, 1.0] from Graph Edit Distance."""
    import math
    import networkx as nx
    if ged is None:
        ged = 0
        for _ in range(approx_steps):
            ged = next(nx.optimize_graph_edit_distance(g1, g2))

    size1 = g1.number_of_nodes() + g1.number_of_edges()
    size2 = g2.number_of_nodes() + g2.number_of_edges()
    total_size = size1 + size2

    if total_size == 0:
        return {"ged": 0.0, "linear_sim": 1.0, "tight_sim": 1.0, "exp_sim": 1.0}

    # Standard Linear Similarity: 1 - GED / (|V1| + |E1| + |V2| + |E2|)
    linear_sim = max(0.0, 1.0 - (ged / total_size))

    # Tight Upper-Bound Similarity (accounts for free node substitutions)
    tight_max = abs(g1.number_of_nodes() - g2.number_of_nodes()) + g1.number_of_edges() + g2.number_of_edges()
    tight_sim = max(0.0, 1.0 - (ged / tight_max)) if tight_max > 0 else 1.0

    # Exponential Similarity
    avg_size = total_size / 2.0
    exp_sim = math.exp(-ged / avg_size)

    return {
        "ged": ged,
        "max_cost": float(total_size),
        "linear_sim": round(linear_sim, 4),
        "tight_sim": round(tight_sim, 4),
        "exp_sim": round(exp_sim, 4),
    }
