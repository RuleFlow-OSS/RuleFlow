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
from core.engine import Event as FlowEvent, SpaceState
from studio.model import Plugin, FlowLangBase


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'output'

        # attributes
        self._render_range: tuple[int, int] = (-100, INF)
        self._space_columns_limit: int = 1
        self._hidden_space_columns: set[int] = set()
        self._columns_control_bitmap: list[bool] = [True, False, False, False, False]

        # connect model signals
        self.model.active_flow.flow.on_evolved_n.connect(self.on_evolved)
        self.model.active_flow.flow.on_undone_n.connect(self.on_undo)
        self.model.active_flow.flow.on_clear.connect(self.on_clear)

        # connect view signals
        self.view.sig_input_submit.connect(self.handle_input_submit)
        self.view.sig_selection_list_toggled.connect(self.handle_selection_toggle)

    def _column_control_bitmap_zero_out(self):
        """Zeros out the column bitmap"""
        self._columns_control_bitmap = [False for _ in range(len(self._columns_control_bitmap))]

    def controls(self) -> Iterator[Widget]:
        self.render_range = Input(value='-100:', id='render-limit')
        self.render_range.border_title = 'Render Range'
        yield self.render_range

        with Collapsible(title='Column Controls', collapsed=False):
            control_bits = self._columns_control_bitmap
            self.column_controls = SelectionList(
                Selection("Event Indices", 0, control_bits[0]),
                Selection("Causal Distance", 1, control_bits[1]),
                Selection("Causally Connected", 2, control_bits[2]),
                Selection(" ├─ Collapsed", 3, control_bits[3]),
                Selection(" ╰─ Counted", 4, control_bits[4]),
                id='column-controls'
            )
            self._rebuild_columns(rebuild_rows=False)  # must be called here or sometime after to initiated columns.
            yield self.column_controls
            self.space_columns_limit = Input(str(self._space_columns_limit), type='integer', id='space-columns-limit')
            self.space_columns_limit.border_title = 'Space Columns Limit'
            yield self.space_columns_limit
            self.hidden_space_columns = Input(id='hidden-space-columns')
            self.hidden_space_columns.border_title = 'Hidden Space Columns'
            yield self.hidden_space_columns

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
            yield Button('Find', id="find-pattern-filters")

        with Collapsible(title='Selection Info', collapsed=False):
            self.selection_info_label = Label('Event Info:\n- Cells: 0\n- Connected: 0\n')
            yield self.selection_info_label
            self.selection_info_label = Label('Cell Info:\n- created at: None\n- destroyed at: None\n')
            yield self.selection_info_label
            self.hover_explorer = Checkbox('Hover Explorer')
            yield self.hover_explorer

        yield Label()

    def handle_input_submit(self, e: Input.Submitted):
        _id: str = e.input.id
        if _id == 'render-limit':
            try:
                rs: list[str] = e.value.strip().split(':')
                self._render_range = (
                    str_to_num(rs[0]) if rs[0] else 0,
                    str_to_num(rs[1]) if rs[1] else INF
                )
                self._rebuild_rows(self.model.active_flow.flow)
            except:
                self.view.notify('Invalid render range.', severity='warning')
                e.input.value = '{0}:{1}'.format(*self._render_range)

        elif _id == 'space-columns-limit':
            try:
                v: int = int(e.value.strip())
                if not 0 <= v <= 1000:
                    raise ValueError
                self._space_columns_limit = int(e.value)
                self._rebuild_columns()
            except:
                self.view.notify('Invalid column space limit. Value must be between 0 and 1000.', severity='warning')
                e.input.value = str(self._space_columns_limit)

        elif _id == 'hidden-space-columns':
            try:
                self._hidden_space_columns.clear()
                values = e.value.replace(' ', '').split(',')
                if values[0] != '':
                    for r in values:
                        if ':' in r:
                            a, b = r.split(':'); a, b = abs(int(a)), abs(int(b))
                            if a > 1000 or b > 1000: raise ValueError
                            for i in range(a, b + 1):
                                self._hidden_space_columns.add(i)
                        else:
                            a = abs(int(r))
                            if a > 1000: raise ValueError
                            self._hidden_space_columns.add(a)
                self._rebuild_columns()
            except:
                self.view.notify('Invalid hidden ranges. Values/Ranges must be between 0 and 1000.', severity='warning')

    def handle_selection_toggle(self, e: SelectionList.SelectionToggled):
        _id: str = e.selection_list.id
        if _id == 'column-controls':
            self._column_control_bitmap_zero_out()
            for i in e.selection_list.selected:
                self._columns_control_bitmap[i] = True
            self._rebuild_columns()

    def panel(self) -> TabPane | None:
        self.data_table = DataTable(id='data-table')
        return TabPane(
            self.name.title(),
            self.data_table
        )

    def on_evolved(self, f: FlowLangBase, steps: int) -> None:
        cft = self.cft
        dt = self.data_table
        if not dt.row_count:
            steps += 1  # to include the first space state
        flush_mode: bool = self._render_range[0] < 0 and is_infinity(self._render_range[1])
        render_limit: int = abs(self._render_range[0])  # only used when flush mode is true
        if flush_mode and steps >= render_limit:
            cft(self._rebuild_rows, f)
        else:
            short_circuit: bool = False  # just a little optimization for large loops
            for event in f.events[-steps:]:
                if short_circuit or flush_mode and dt.row_count >= render_limit:
                    short_circuit = True
                    cft(lambda: dt.remove_row(dt.coordinate_to_cell_key(Coordinate(0, 0)).row_key))
                cft(self._add_row, event)
        cft(self._refresh_column_widths)
        if not flush_mode:
            dt.scroll_end(animate=False)

    def on_undo(self, f: FlowLangBase, steps: int) -> None:
        # NOTE: this function is not very optimized for updates, but premature optimization is the root of all evil.
        cft = self.cft
        dt = self.data_table
        old_rows_count = len(f.events) + steps
        for i in range(steps):
            try: cft(dt.remove_row, str(old_rows_count - i - 1))
            except: pass
        if self._render_range[0] < 0 and is_infinity(self._render_range[1]):  # if flushing
            cft(self._rebuild_rows, f)
        cft(self._refresh_column_widths)

    def on_clear(self):
        self.cft(self.data_table.clear)

    def _add_row(self, event: FlowEvent):
        columns = []

        # Process the info columns
        control_bitmap = self._columns_control_bitmap
        if control_bitmap[2]:
            if control_bitmap[3]:  # if we are collapsing it
                connected = set(event.causally_connected_events)
            else:
                connected = tuple(event.causally_connected_events)
            if control_bitmap[4]:  # if we are counting the causally connect (to display that metric instead)
                connected = len(connected)
        else:
            connected = None
        for data, show in zip((event.time,
                               event.causal_distance_to_creation,
                               connected),
                              control_bitmap):
            if show: columns.append(data)

        # Process the space columns
        spaces: Iterator[SpaceState] = event.spaces
        hidden: set[int] = self._hidden_space_columns
        for i in range(self._space_columns_limit):
            try:
                space = spaces.__next__()  # we must always increment next (even though it may be hidden, that is what makes the check work)
                if i in hidden:
                    continue
                columns.append(space)
            except StopIteration:
                break

        # Add everything as a row
        self.data_table.add_row(
            *columns,
            key=str(event.time)
        )

    def _rebuild_rows(self, f: FlowLangBase) -> None:
        a, b = self._render_range
        self.data_table.clear()
        for event in f.events[a:b + (1 if b > 0 else 0)]:
            self._add_row(event)
        self._refresh_column_widths()

    def _rebuild_columns(self, rebuild_rows: bool = True) -> None:
        dt = self.data_table
        dt.clear(columns=True)
        if self._columns_control_bitmap[0]:
            dt.add_column('Event', key='event')
        if self._columns_control_bitmap[1]:
            dt.add_column('Distance', key='distance')
        if self._columns_control_bitmap[2]:
            dt.add_column('Connected', key='connected')
        hidden: set[int] = self._hidden_space_columns
        for i in range(self._space_columns_limit):
            if i in hidden:
                continue
            dt.add_column(_:=str(i), key=_)
        if rebuild_rows:
            self._rebuild_rows(self.model.active_flow.flow)

    def _refresh_column_widths(self) -> None:
        """Update the column widths as Textual does not currently do that for us when removing rows."""
        dt = self.data_table
        if 0 <= (rc:=(dt.row_count - 1)):
            # noinspection PyProtectedMember
            dt._update_column_widths(
                {dt.coordinate_to_cell_key(Coordinate(rc, i)) for i in range(len(dt.columns))}
            )

plugin = P()
