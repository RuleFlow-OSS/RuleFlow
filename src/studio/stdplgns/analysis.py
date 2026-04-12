# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, Label
from textual.widget import Widget
from textual.containers import ScrollableContainer

# Standard Imports
from typing import Iterator
from studio.model import Plugin


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'analysis'

    def panel(self) -> TabPane | None:
        return TabPane(self.name.title())

    def controls(self) -> Iterator[Widget]:
        with Collapsible(title='Causal Network', collapsed=False):
            self.live_causal_network = Checkbox('Live Mode')
            yield self.live_causal_network
            self.initial_causal_network_node = Input(type='number', value='0')
            self.initial_causal_network_node.border_title = 'Initial Event'
            yield self.initial_causal_network_node
            self.aggregate_branches = Input()
            self.aggregate_branches.border_title = 'Aggregate Branches'
            yield self.aggregate_branches

        with Collapsible(title='Branch Graph', collapsed=False):
            self.live_branch_network = Checkbox('Live Mode')
            yield self.live_branch_network
            self.branch_network_range = Input()
            self.branch_network_range.border_title = 'Selected Branches'
            yield self.branch_network_range

        with Collapsible(title='Growth Metrics', collapsed=False):
            yield Label("""Algorithm Controls for \ndetermining network or \nevolution properties such \nas dimension or sparseness.""")

        with Collapsible(title='VisJS Network Viewer', collapsed=True):
            yield Label("Options for the web \ngraph renderer.")


plugin = P()
