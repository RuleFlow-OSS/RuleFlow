"""
This plugin provides an exploratory environment for the evolutions of cellular systems.
"""
# Textual Imports
from rich.text import Text
from textual.widgets import (Collapsible, TabPane, Input, Select,
                             Checkbox, Label, DataTable as _DataTable, SelectionList, ContentSwitcher)
from textual.widgets.data_table import CellKey
from textual.widget import Widget
from textual.coordinate import Coordinate
from textual.widgets.selection_list import Selection
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.events import MouseMove

# Standard Imports
from typing import Iterator, Sequence, cast
from core.numlib import INF, str_to_num, is_infinity
from core.engine import Event as FlowEvent, SpaceState, Cell as FlowCell, DeltaCell, DeltaSpace, DeltaSpaces
from core.prettier import SpaceStateStringFormatter
from core.signals import Signal
from lang.implementation import BaseRule
from studio.model import Plugin, FlowLangBase


class DataTable(_DataTable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sig_mouse_over_inner_cell: Signal[Coordinate | None, int] = Signal()
        self.enabled_sig_mouse_over_space_cell: bool = False

    def on_mouse_move(self, event: MouseMove) -> None:
        if not self.enabled_sig_mouse_over_space_cell:
            return
        # Grab the row/col directly from the exact terminal cell the mouse is touching.
        meta = event.style.meta  # metadata holds the row and column info
        # If the mouse is over the header or the empty space below the table, this metadata won't exist.
        if not meta or "row" not in meta or "column" not in meta or meta['row'] == -1:
            self.sig_mouse_over_inner_cell.emit(None, 0)
            return
        coord = Coordinate(meta["row"], meta["column"])
        start_x = 0
        PADDING = self.cell_padding
        columns = list(self.columns.values())
        for i in range(coord.column):  # Calculate start_x ONLY for columns BEFORE the hovered one
            col = columns[i]
            if col.auto_width:
                base_width = max(col.width or 0, col.content_width or 0)
            else:
                base_width = col.width or col.content_width or 0
            # Add this column's total footprint (width + 1 left pad + 1 right pad)
            start_x += base_width + 2 * PADDING
        # Calculate the specific character offset inside the cell
        virtual_x = event.x + self.scroll_offset.x
        # Subtract start_x to zero out the column, then subtract 1 for THIS column's left padding
        char_offset = (virtual_x - start_x) - PADDING

        # emit the signal
        self.sig_mouse_over_inner_cell.emit(coord, char_offset)


class RulesetDashboard(VerticalScroll):
    """A scoped container specifically for the ruleset layout."""

    DEFAULT_CSS = """
    RulesetDashboard Horizontal {
        height: auto;
        width: 100%;
    }
    RulesetDashboard Vertical {
        width: 1fr;
        height: auto;
        margin-right: 1;
    }
    """


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'explore'

        # tools
        self.space_state_formatter: SpaceStateStringFormatter = SpaceStateStringFormatter()
        self._cell_ids_to_highlight: frozenset[int] = frozenset()

        # attributes
        self._render_range: tuple[int, int, int] = (-100, INF, 1)
        self._space_columns_limit: int = 1
        self._hidden_space_columns: set[int] = set()
        self._columns_control_bitmap: list[bool] = [True, False, False, False, False, False]

        # connect model signals
        self.model.flow.on_evolved_n.connect(self.on_evolved)
        self.model.flow.on_undone_n.connect(self.on_undo)
        self.model.flow.on_clear.connect(self.on_clear)
        self.model.flow.on_ruleset_set.connect(
            lambda f: self.cft(self._rebuild_ruleset_table, f.ruleset.rules, self.ruleset_table)
        )

        # connect view signals
        self.view.sig_input_submit.connect(self.handle_input_submit)
        self.view.sig_selection_list_toggled.connect(self.handle_selection_toggle)
        self.view.sig_checkbox_changed.connect(self.handle_checkbox_change)

        # temp trackers
        self.__last_hover_coord_and_offset: tuple[Coordinate, int] = (Coordinate(0, 0), 0)

    def _column_control_bitmap_zero_out(self):
        """Zeros out the column bitmap"""
        self._columns_control_bitmap = [False for _ in range(len(self._columns_control_bitmap))]

    def controls(self) -> Iterator[Widget]:
        self.render_range = Input(value='-100:', placeholder='e.g. -10: or 3:10', id='render-limit')
        self.render_range.border_title = 'Render Range'
        yield self.render_range
        self.show_ruleset = Checkbox('Show Ruleset', value=True, id='show-ruleset')
        yield self.show_ruleset

        with Collapsible(title='Column Controls', collapsed=False):
            control_bits = self._columns_control_bitmap
            self.column_controls = SelectionList(
                Selection("Event Indices", 0, control_bits[0]),
                Selection("Causal Distance", 1, control_bits[1]),
                Selection("Causally Connected", 2, control_bits[2]),
                Selection(" ├─ Unique", 3, control_bits[3]),
                Selection(" ├─ Sorted", 4, control_bits[4]),
                Selection(" ╰─ Counted", 5, control_bits[5]),
                id='column-controls'
            )
            self._rebuild_columns(rebuild_rows=False)  # must be called here or sometime after to initiated columns.
            yield self.column_controls
            self.space_columns_limit = Input(str(self._space_columns_limit), type='integer', id='space-columns-limit')
            self.space_columns_limit.border_title = 'Space Columns Limit'
            yield self.space_columns_limit
            self.hidden_space_columns = Input(placeholder='e.g. 5, 10:15, 20', id='hidden-space-columns')
            self.hidden_space_columns.border_title = 'Hidden Space Columns'
            yield self.hidden_space_columns

        with Collapsible(title='Cell Rendering', collapsed=False):
            self.style_controls = SelectionList(
                Selection("Cell Styling", 0, True),
                Selection(" ╰─ On Symbol", 1, False),
                Selection("Show Symbols", 2, True),
                Selection("Cell Padding", 3, True),
                Selection("Clear on Override", 4, False),
                id='style-controls'
            )
            yield self.style_controls
            self.style_map = Input("auto", placeholder='e.g. auto or A: red', id='style-map')
            self.style_map.border_title = 'Style Override'
            yield self.style_map
            self.symbol_map = Input("auto", placeholder='e.g. auto or A: Z', id='symbol-map')
            self.symbol_map.border_title = 'Symbol Map'
            yield self.symbol_map

        with Collapsible(title='Hover Explorer', collapsed=False):
            self.hovered_info_label = Label()
            self._reset_hovered_info_label()
            yield self.hovered_info_label
            self.hover_explorer = Checkbox('Hover Explorer', id='hover-explorer')
            yield self.hover_explorer
            self.hover_ruleset_enabled = Checkbox('Hovered Event Ruleset', disabled=True, id='hover-ruleset-enabled')
            yield self.hover_ruleset_enabled
            self.hover_style = Input("on black", placeholder='e.g. on red or bold blue', id='hover-style')
            self.hover_style.border_title = 'Hover Style'
            yield self.hover_style

        yield Label()

    def handle_input_submit(self, e: Input.Submitted):
        _id: str = e.input.id
        if _id == 'render-limit':
            try:
                rs: list[str] = e.value.strip().split(':')
                if len(rs) == 2: rs.append('')  # it must always be 3 things
                self._render_range = (
                    int(rs[0]) if rs[0] else 0,
                    str_to_num(rs[1]) if rs[1] else INF,
                    abs(int(rs[2])) if rs[2] else 1
                )
                self._rebuild_rows()
            except:
                self.view.notify('Invalid render range.', severity='warning')
                e.input.value = '{0}:{1}:{2}'.format(*self._render_range)

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

        elif _id in ('style-map', 'symbol-map'):
            self._handle_styling_update()

        elif _id == 'hover-style':
            self.space_state_formatter.cell_id_style = e.value.strip()

    def handle_selection_toggle(self, e: SelectionList.SelectionToggled):
        _id: str = e.selection_list.id
        if _id == 'column-controls':
            self._column_control_bitmap_zero_out()
            for i in e.selection_list.selected:
                self._columns_control_bitmap[i] = True
            self._rebuild_columns()
        if _id == 'style-controls':
            self._handle_styling_update()

    def handle_checkbox_change(self, e: Checkbox.Changed):
        _id: str = e.checkbox.id
        if _id == 'hover-explorer':
            self.data_table.enabled_sig_mouse_over_space_cell = e.value
            self.hover_ruleset_enabled.disabled = not e.value
            if not e.value:
                self.hover_ruleset_enabled.value = self.hovered_ruleset_container.display = False
                self._reset_hovered_info_label()
                self._cell_ids_to_highlight = frozenset()
        if _id == 'hover-ruleset-enabled' and self.hover_explorer.value:
            self.hovered_ruleset_container.display = e.value
            if not e.value:
                self.hovered_ruleset_table.clear()
        if _id == 'show-ruleset':
            self.ruleset_container.display = e.value

    def panel(self) -> TabPane | None:
        # Ruleset Table
        self.ruleset_table = _DataTable(id='ruleset-table', show_cursor=False)
        self.ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.ruleset_container = Vertical(
            Label('[bold] Active Ruleset Table [/bold]'),
            self.ruleset_table
        )

        # Ruleset Table
        self.hovered_ruleset_table = _DataTable(id='hovered-ruleset-table', show_cursor=False)
        self.hovered_ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.hovered_ruleset_container = Vertical(
            Label('[bold] Hovered Event Ruleset Table [/bold]'),
            self.hovered_ruleset_table,
        )
        self.hovered_ruleset_container.display = False

        # Evolution Table
        self.data_table = DataTable(id='data-table')
        self.data_table.sig_mouse_over_inner_cell.connect(self._handle_mouse_over_data_table)
        return TabPane(
            self.name.title(),
            RulesetDashboard(
                Horizontal(
                    self.ruleset_container,
                    self.hovered_ruleset_container
                ),
                Label('[bold] Evolution Table [/bold]'),
                self.data_table
            )
        )

    def _handle_styling_update(self):
        control_bitmap: list[bool] = [False, False, False, False, False]
        for i in self.style_controls.selected: control_bitmap[i] = True

        try:
            style_map: dict[str, str] = {
                k.strip(): v.strip() for k, v in (p.split(':') for p in self.style_map.value.split(','))
            } if self.style_map.value != 'auto' else None

            symbol_map: dict[str, str] = {
                k.strip(): v.strip() for k, v in (p.split(':') for p in self.symbol_map.value.split(','))
            } if self.symbol_map.value != 'auto' else None
        except:
            self.view.notify('Invalid style map.', severity='error')
            return

        # noinspection PyTypeChecker
        self.space_state_formatter.config(
            *control_bitmap[:4],
            style_map,
            control_bitmap[4],
            symbol_map
        )

        # noinspection PyTypeChecker
        self._rebuild_ruleset_table(self.model.flow.ruleset.rules, self.ruleset_table)
        self._rebuild_rows()

    def _reset_hovered_info_label(self):
        self.hovered_info_label.content = """[bold]Event Info[/bold]
• ----
• ----
• ----
• ----
• ----
• ----
• ----

[bold]Cell Info[/bold]
• ----
• ----
• ----
• ----
"""

    def _handle_mouse_over_data_table(self, coord: Coordinate | None, offset: int) -> None:
        def reset_highlighted():
            self._reset_hovered_info_label()
            if self._cell_ids_to_highlight:
                self._cell_ids_to_highlight = frozenset()
                self._rebuild_rows()
        if (not coord
                or offset == -1
                or self.data_table.coordinate_to_cell_key(coord).column_key in ('event', 'distance', 'connected')):
            reset_highlighted()
            return

        # calculate offset of the cell index (because of different padding/rendering options)
        cell_content: str = str(self.data_table.get_cell_at(coord))
        if cell_content.startswith(' '):  # if padding of " " around symbols is being used.
            if cell_content.startswith('  '):  # if not rendering symbols but blocks of "  "
                offset = offset // 2  # one extra symbol needs to be removed
            else:
                offset = offset // 3  # two extra symbols need to be removed

        # if the last cell was the same
        if self.__last_hover_coord_and_offset == (coord, offset):
            return
        self.__last_hover_coord_and_offset = (coord, offset)

        cell_key: CellKey = self.data_table.coordinate_to_cell_key(coord)
        row_idx: int = int(cell_key.row_key.value)
        column_idx: int = int(cell_key.column_key.value)

        # grab all relevant information about the selected space
        flow: FlowLangBase = self.model.flow
        event: FlowEvent = flow.events[row_idx]
        spaces: tuple[tuple[DeltaSpaces, DeltaSpace, SpaceState], ...] = tuple(event.spaces_with_metadata)
        space_state: SpaceState = spaces[column_idx][2]

        # update the rows
        if offset >= len(space_state):
            reset_highlighted()
            return
        flow_cell: FlowCell = space_state.get_all_cells()[offset]
        self._cell_ids_to_highlight = frozenset((id(flow_cell),))
        self._rebuild_rows()

        # update the hover info labels
        try:
            affected_cells: DeltaCell = tuple(event.affected_cells)[column_idx]
            created_cells: int = len(affected_cells.new_cells)
            destroyed_cells: int = len(affected_cells.destroyed_cells)
        except IndexError:
            created_cells: None = None
            destroyed_cells: None = None
        try:  # in separate try block because of the destroyed_at maybe not existing
            cell_destroyed_at: int = flow_cell.destroyed_at[column_idx]
            lifespan: int = cell_destroyed_at - flow_cell.created_at
        except IndexError:
            cell_destroyed_at: None = None
            lifespan: None = None
        connected_events = tuple(event.causally_connected_events)
        self.hovered_info_label.content = f"""[bold]Event #{event.time} | Space #{column_idx}[/bold]
• Branched Spaces: {len(spaces) - 1}
• Space Size: {len(space_state)}
• Causal Distance: {event.causal_distance_to_creation}
• Connected Total: {len(connected_events)}
• Connected Unique: {len(set(connected_events))}
• Created Cells: {created_cells}
• Destroyed Cells: {destroyed_cells}

[bold]Cell #{offset}[/bold]
• Quanta: {flow_cell.quanta}
• Created at: {flow_cell.created_at}
• Destroyed at: {cell_destroyed_at}
• Lifespan: {lifespan}
"""

        # place the rule (and its chain if there is one) in the hovered ruleset table.
        if self.hover_ruleset_enabled.value:
            applied_rule: BaseRule = spaces[column_idx][0].rule
            if applied_rule:
                self._rebuild_ruleset_table(applied_rule.chain, self.hovered_ruleset_table, hide_disabled=True, remember_old_row_length=True)

    def _rebuild_ruleset_table(self, rules: Sequence[BaseRule],
                               table: DataTable,
                               hide_disabled: bool = False,
                               remember_old_row_length: bool = False) -> None:
        # we have the f parameter because this is called by a Flow signal.
        def print_rule(rule: BaseRule) -> tuple[Text, Text]:
            selectors: list[Text] = []
            for s in rule.selector:
                sv = s.selector
                if isinstance(sv, str | bytes):
                    selectors.append(self.space_state_formatter.convert_pure_str(sv))
                else:
                    selectors.append(Text(str(sv)))
            targets: list[Text] = []
            for t in rule.target:
                tv = t.target
                if isinstance(tv, int):
                    targets.append(Text(str(tv)))
                else:  # when `tv` is Sequence[Cell]
                    targets.append(self.space_state_formatter.convert_pure_str(''.join(str(c) for c in tv)))
            return (Text(', ').join(selectors) if len(selectors) > 1 else selectors[0],
                    Text(', ').join(targets) if len(targets) > 1 else targets[0])

        old_rows: int = table.row_count
        table.clear()
        rule: BaseRule
        for i, rule in enumerate(rules):
            if hide_disabled and rule.disabled:
                continue
            table.add_row(
                *print_rule(rule), rule.__class__.__name__, rule.group,
                label=str(i)
            )
            old_rows -= 1
        if remember_old_row_length and old_rows:
            for _ in range(old_rows): table.add_row()

    def on_evolved(self, f: FlowLangBase, steps: int) -> None:
        cft = self.cft
        dt = self.data_table
        if not dt.row_count:
            steps += 1  # to include the first space state
        flush_mode: bool = self._render_range[0] < 0 and is_infinity(self._render_range[1])
        render_limit: int = abs(self._render_range[0])  # only used when flush mode is true
        if flush_mode and steps >= render_limit:
            cft(self._rebuild_rows)
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
            cft(self._rebuild_rows)
        cft(self._refresh_column_widths)

    def on_clear(self):
        try:
            self.cft(self.data_table.clear)
        except RuntimeError:  # this function may or may not be called within the main thread.
            self.data_table.clear()

    def _add_row(self, event: FlowEvent):
        columns = []

        # Process the info columns
        control_bitmap = self._columns_control_bitmap
        if control_bitmap[2]:
            if control_bitmap[3]:  # if we are collapsing it
                connected = set(event.causally_connected_events)
            else:
                connected = tuple(event.causally_connected_events)
            if control_bitmap[5]:  # if we are counting the causally connect (to display that metric instead)
                connected = len(connected)
            elif control_bitmap[4]:
                connected = sorted(connected)
        else:
            connected = None  # just to satisfy the IDE wanting a name in the space
        for data, show in zip((event.time,
                               event.causal_distance_to_creation,
                               connected),
                              control_bitmap):
            if show: columns.append(data)

        # Process the space columns
        spaces: Iterator[SpaceState] = event.spaces
        formatter: SpaceStateStringFormatter = self.space_state_formatter
        cells_to_highlight: frozenset[int] = self._cell_ids_to_highlight
        hidden: set[int] = self._hidden_space_columns
        for i in range(self._space_columns_limit):
            try:
                space = spaces.__next__()  # we must always increment next (even though it may be hidden, that is what makes the check work)
                if i in hidden:
                    continue
                columns.append(formatter(space, cells_to_highlight))
            except StopIteration:
                break
        # Add everything as a row
        self.data_table.add_row(
            *columns,
            key=str(event.time)
        )

    def _rebuild_rows(self) -> None:
        a, b, c = self._render_range
        dt = self.data_table
        old_x, old_y = dt.scroll_x, dt.scroll_y
        dt.clear()
        for event in self.model.flow.events[a:b + (1 if b > 0 else 0):c]:
            self._add_row(event)
        self._refresh_column_widths()
        dt.scroll_to(x=old_x, y=old_y, animate=False)

    def _rebuild_columns(self, rebuild_rows: bool = True) -> None:
        dt = self.data_table
        old_x, old_y = dt.scroll_x, dt.scroll_y
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
            self._rebuild_rows()
        dt.scroll_to(x=old_x, y=old_y, animate=False)

    def _refresh_column_widths(self) -> None:
        """Update the column widths as Textual does not currently do that for us when removing rows."""
        dt = self.data_table
        if 0 <= (rc:=(dt.row_count - 1)):
            # noinspection PyProtectedMember
            dt._update_column_widths(
                {dt.coordinate_to_cell_key(Coordinate(rc, i)) for i in range(len(dt.columns))}
            )

plugin = P()
