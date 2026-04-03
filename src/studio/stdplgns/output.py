# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Label, DataTable
from rich.text import Text
from textual.widgets.data_table import CellKey
from textual.widget import Widget
from textual.coordinate import Coordinate
from textual.containers import ScrollableContainer

# Standard Imports
from typing import Iterator
from studio.model import Plugin, FlowLang


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'output'

        # plugin attributes
        # # TODO: work on this
        # self._color_map: dict[str, Text] = {
        #     l: Text(l) for l in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        # }

        # connect model signals
        self.model.active_flow.flow.on_evolve.connect(self.on_evolved)
        self.model.active_flow.flow.on_undo.connect(self.on_undo)
        self.model.active_flow.flow.on_clear.connect(self.on_clear)

        # connect view signals
        self.view.sig_checkbox_changed.connect(self.handle_checkbox)

    def controls(self) -> Iterator[Widget]:
        self.live_step = Checkbox('Live Step')  # update on each step, rather than the end of an evolution.
        yield self.live_step

        with Collapsible(title='Pattern Queries', collapsed=False):
            self.search_pattern = Input()
            self.search_pattern.border_title = 'Search Pattern'
            yield self.search_pattern
            self.created_at = Input()
            self.created_at.border_title = 'Created at Event(s)'
            yield self.created_at
            self.destroyed_at = Input()
            self.destroyed_at.border_title = 'Destroyed at Event(s)'
            yield self.destroyed_at
            self.highlight_matches = Checkbox('Highlight all matching events')
            yield self.highlight_matches

        with Collapsible(title='Selection Info', collapsed=False):
            self.selection_info_label = Label('Selection Info:\n- created at: None\n- destroyed at: None')
            yield self.selection_info_label
            self.enable_hover_highlighting = Checkbox('Enable Hover Highlighting')
            yield self.enable_hover_highlighting

        with Collapsible(title='Column Controls', collapsed=True):
            self.show_event_indices = Checkbox('Show Event Indices')
            yield self.show_event_indices
            self.show_causally_connected = Checkbox('Show Causally connected')
            yield self.show_causally_connected

        with Collapsible(title='Color Controls', collapsed=True):
            self.color_mapping = Input()
            self.color_mapping.border_title = 'Color Mapping'
            yield self.color_mapping

    def handle_checkbox(self, sig: Checkbox.Changed) -> None:
        pass

    def panel(self) -> TabPane | None:
        self.data_table = DataTable(id='data-table')
        self.data_table.add_columns('Time')
        self.data_table.add_columns('Distance')
        self.data_table.add_columns('Causally Connected')
        self.data_table.add_columns('Evolution')

        return TabPane(
            self.name.title(),
            self.data_table
        )

    def on_evolved(self):
        # noinspection PyTypeChecker
        flow: FlowLang = self.model.active_flow.flow
        self.data_table.add_row(
            str(flow.current_event.time),
            str(flow.current_event.causal_distance_to_creation),
            str(tuple(flow.current_event.causally_connected_events)),
            str(flow.current_event.spaces.__next__()).replace('A', '[on blue3] A [/on blue3]')
            .replace('B', '[on magenta] B [/on magenta]')
            .replace('C', '[on yellow] C [/on yellow]')
        )
        if self.data_table.is_vertical_scroll_end:
            self.data_table.scroll_end(x_axis=False, animate=False)

    def on_undo(self):
        cell_key: CellKey = self.data_table.coordinate_to_cell_key(Coordinate(self.data_table.row_count - 1, 0))
        self.data_table.remove_row(cell_key.row_key)
        if self.data_table.is_vertical_scroll_end:
            self.data_table.scroll_end(x_axis=False, animate=False)

    def on_clear(self):
        self.data_table.clear()

plugin = P()
