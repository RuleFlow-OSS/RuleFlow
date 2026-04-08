# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Label, DataTable, SelectionList, Button
from rich.text import Text
from textual.widgets.data_table import CellKey
from textual.widget import Widget
from textual.coordinate import Coordinate
from textual.widgets.selection_list import Selection

# Standard Imports
from typing import Iterator
from core.numlib import INF, str_to_num, is_infinity
from core.engine import Event as FlowEvent
from studio.model import Plugin, FlowLangBase


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'output'

        # attributes
        self._render_range: tuple[int, int] = (-100, INF)

        # connect model signals
        self.model.active_flow.flow.on_evolved_n.connect(self.on_evolved)
        self.model.active_flow.flow.on_undone_n.connect(self.on_undo)
        self.model.active_flow.flow.on_clear.connect(self.on_clear)

        # connect view signals
        self.view.sig_checkbox_changed.connect(self.handle_checkbox)
        self.view.sig_input_submit.connect(self.handle_input_submit)

    def controls(self) -> Iterator[Widget]:
        self.render_range = Input(value='-100:', id='render-limit')
        self.render_range.border_title = 'Render Range'
        yield self.render_range

        with Collapsible(title='Column Controls', collapsed=False):
            self.hidden_space_columns = Input()
            self.hidden_space_columns.border_title = 'Hidden spaces'
            yield self.hidden_space_columns
            self.column_controls = SelectionList(
                Selection("Event indices", 0, True),
                Selection("Causal distance", 1, True),
                Selection("Causally connected", 2, True),
                Selection(" ├─ Collapsed", 3, False),
                Selection(" ╰─ Counted", 4, False)
            )
            yield self.column_controls

        with Collapsible(title='Pattern Queries', collapsed=False):
            self.search_pattern = Input()
            self.search_pattern.border_title = 'Search pattern'
            yield self.search_pattern
            self.created_at = Input()
            self.created_at.border_title = 'Created at event(s)'
            yield self.created_at
            self.destroyed_at = Input()
            self.destroyed_at.border_title = 'Destroyed at event(s)'
            yield self.destroyed_at
            yield Button('Find', id="find-pattern-filters")

        with Collapsible(title='Selection Info', collapsed=False):
            self.selection_info_label = Label('Event Info:\n- Cells: 0\n- Connected: 0\n')
            yield self.selection_info_label
            self.selection_info_label = Label('Cell Info:\n- created at: None\n- destroyed at: None\n')
            yield self.selection_info_label
            self.hover_explorer = Checkbox('Hover explorer')
            yield self.hover_explorer

        yield Label()

    def handle_checkbox(self, e: Checkbox.Changed) -> None:
        pass

    def handle_input_submit(self, e: Input.Submitted):
        _id: str = e.input.id
        if _id == 'render-limit':
            try:
                rs: list[str] = e.value.strip().split(':')
                self._render_range = (
                    str_to_num(rs[0]) if rs[0] else 0,
                    str_to_num(rs[1]) if rs[1] else INF
                )
                self._update_rows(self.model.active_flow.flow)
            except:
                self.view.notify('Invalid render range', severity='error')
                e.input.value = '{0}:{1}'.format(*self._render_range)

    def panel(self) -> TabPane | None:
        self.data_table = DataTable(id='data-table')
        self.data_table.add_column('Time', key='time')
        self.data_table.add_column('Distance', key='distance')
        self.data_table.add_column('Connected', key='connected')
        self.data_table.add_column('Evolution', key='evolution')

        # col = self.data_table.get_column('connected')
        # col = 0
        # self.data_table.refresh()

        return TabPane(
            self.name.title(),
            self.data_table
        )

    def _add_row(self, event: FlowEvent):
        self.data_table.add_row(  # maybe make a separate add_row()
            event.time,
            event.causal_distance_to_creation,
            tuple(event.causally_connected_events),
            str(event.spaces.__next__())
            .replace('A', '[on blue3] A [/on blue3]')
            .replace('B', '[on magenta] B [/on magenta]')
            .replace('C', '[on yellow] C [/on yellow]'),
            key=str(event.time)
        )

    def _update_rows(self, f: FlowLangBase) -> None:
        a, b = self._render_range
        self.on_clear()
        for event in f.events[a:b + (1 if b > 0 else 0)]:
            self._add_row(event)
        self._refresh_column_widths()

    def on_evolved(self, f: FlowLangBase, steps: int) -> None:
        dt = self.data_table
        if not dt.row_count:
            steps += 1  # to include the first space state
        flush_mode: bool = self._render_range[0] < 0 and is_infinity(self._render_range[1])
        render_limit: int = abs(self._render_range[0])  # only used when flush mode is true
        if flush_mode and steps >= render_limit:
            self._update_rows(f)
        else:
            short_circuit: bool = False  # just a little optimization for large loops
            for event in f.events[-steps:]:
                if short_circuit or flush_mode and dt.row_count >= render_limit:
                    short_circuit = True
                    self.cft(lambda: dt.remove_row(dt.coordinate_to_cell_key(Coordinate(0, 0)).row_key))
                self.cft(self._add_row, event)
        self._refresh_column_widths()
        if not flush_mode:
            dt.scroll_end(animate=False)

    def on_undo(self, f: FlowLangBase, steps: int) -> None:
        cft = self.cft
        dt = self.data_table
        if (_:=dt.row_count) < steps:
            steps = _
        for _ in range(steps):
            cft(dt.remove_row, str(dt.row_count - 1))
        self._refresh_column_widths()

    def on_clear(self):
        self.data_table.clear()

    def _refresh_column_widths(self) -> None:
        """Update the column widths as Textual does not currently do that for us when removing rows."""
        dt = self.data_table
        if 0 <= (rc:=(dt.row_count - 1)):
            # noinspection PyProtectedMember
            dt._update_column_widths(
                {dt.coordinate_to_cell_key(Coordinate(rc, i)) for i in range(len(dt.columns))}
            )

plugin = P()
