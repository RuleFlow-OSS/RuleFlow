"""
This plugin provides an exploratory environment for the evolutions of cellular systems.

Policy:
- This plugin should primarily focus on a single space at a time (given by some coordinate system). Another plugin
(or table widget within this plugin) should be developed for multiple space explorations.

Future Features:
- ctrl+h when hovering over a cell should hold the highlight (add it to the highlight setting).
"""

# Textual Imports
from rich.text import Text
from textual.widgets import (Collapsible, Button, TabPane, Input, Checkbox, Label, DataTable as _DataTable, SelectionList, RadioSet)
from textual.widgets.data_table import CellKey
from textual.widget import Widget
from textual.coordinate import Coordinate
from textual.widgets.selection_list import Selection
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.events import MouseMove

# Standard Imports
from typing import Iterator, Sequence
from core.numlib import INF, str_to_num, is_infinity
from core.engine import Event as FlowEvent, Cell as FlowCell, DeltaCell, DeltaSpace, DeltaSpaces, Coordinate as SpaceCoordinate
from core.topologies.nd_space import SpaceState1D as SpaceState
from core.topologies.tooling.prettier import SpaceState1DFormatter
from core.signals import Signal
from lang.implementation import BaseRule
from studio.model import Plugin
from lang.interpreter import FlowLang


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
        padding = self.cell_padding
        columns = list(self.columns.values())
        for i in range(coord.column):  # Calculate start_x ONLY for columns BEFORE the hovered one
            col = columns[i]
            if col.auto_width:
                base_width = max(col.width or 0, col.content_width or 0)
            else:
                base_width = col.width or col.content_width or 0
            # Add this column's total footprint (width + 1 left pad + 1 right pad)
            start_x += base_width + 2 * padding
        # Calculate the specific character offset inside the cell
        virtual_x = event.x + self.scroll_offset.x
        # Subtract start_x to zero out the column, then subtract 1 for THIS column's left padding
        char_offset = (virtual_x - start_x) - padding

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
    name = 'explore'
    file_types = ['.flow', '.pflow', '.wpflow']

    @property
    def flow(self) -> FlowLang:
        return self.model.data.setdefault('flow', FlowLang())

    def on_initialized(self) -> None:
        # tools
        self.space_formatter: SpaceState1DFormatter = SpaceState1DFormatter()
        self._cell_ids_to_highlight: frozenset[int] = frozenset()

        # attributes
        self._render_range: tuple[int, int, int] = (-100, -1, 1)
        self._space_coordinate: SpaceCoordinate = SpaceCoordinate(-1, 0)
        self._columns_controls = (  # (control title, column title | None, control key, default value)
            ("Space Index", 'Space Idx', 'space-idx', True),
            ("Cell Count", 'Cells', 'cell-count', False),
            ("Created Cells", 'Created', 'created-cells', False),
            ("Destroyed Cells", 'Destroyed', 'destroyed-cells', False),
            ("Causal Distance", 'Distance', 'causal-distance', False),
            ("Causally Connected", 'Connected', 'causally-connected', False),
            ("├─ Show List", None, 'show-causal-list', False),
            ("│  ╰─ Sorted", None, 'show-sorted-causal-list', False),
            ("╰─ Unique", None, 'show-unique-causal-list', False),
            ("   ╰─ Separate", None, 'show-seperate-unique-causal-list', False),
            ("Show Space", None, 'show-space', True)
        )
        self._render_controls = (  # (control title, control key, default value)
            ("Cell Styling", 'cell-styling', True),
            ("├─ On Symbol", 'cell-styling-on-symbol', False),
            ("╰─ Clear on Override", 'clear-styling-on-override', False),
            ("Show Symbols", 'show-symbols', True),
            ("╰─ Encode Ordinals", 'show-encoded-symbols', True),
        )

        # connect model signals
        self.flow.on_evolved_n.connect(self.on_evolved)
        self.flow.on_undone_n.connect(self.on_undo)
        self.flow.on_clear.connect(self.on_clear)
        self.flow.on_ruleset_set.connect(
            lambda: self.cft(self._rebuild_ruleset_table, self.flow.ruleset.rules, self.ruleset_table)
        )

        # connect view signals
        self.view.sig_input_submit.connect(self.handle_input_submit)
        self.view.sig_selection_list_toggled.connect(self.handle_selection_toggle)
        self.view.sig_checkbox_changed.connect(self.handle_checkbox_change)

        # temp trackers
        self.__last_hover_coord_and_offset: tuple[Coordinate, int] = (Coordinate(0, 0), 0)

    def controls(self) -> Iterator[Widget]:
        self.render_range = Input(value='-100:', placeholder='e.g. -10: or 3:10', id='render-range')
        self.render_range.border_title = 'Render Range'
        yield self.render_range
        self.space_coordinate = Input(str(self._space_coordinate), placeholder='e.g. (4, 2)', id='space-coordinate')  # (FUTURE SUPPORT FOR MULTIPLE SPACE COLUMNS)
        self.space_coordinate.border_title = 'Space Coordinate'
        yield self.space_coordinate
        self.show_ruleset = Checkbox('Show Ruleset', value=True, id='show-ruleset')
        yield self.show_ruleset

        with Collapsible(title='Column Controls', collapsed=False):
            self.column_controls = SelectionList(
                *(Selection(c[0], c[2], c[3]) for c in self._columns_controls),
                id='column-controls'
            )
            self._rebuild_columns(rebuild_rows=False)  # must be called here or sometime after to initiate columns.
            yield self.column_controls

        with Collapsible(title='Cell Rendering', collapsed=False):
            self.cell_width = Input('3', type='integer', id='cell-width')
            self.cell_width.border_title = 'Cell Width'
            yield self.cell_width

            # property based controls
            self.encode_property = RadioSet('Quanta', 'Generation', 'Identity')
            self.encode_property.border_title = 'Encode Property'
            yield self.encode_property
            self.style_property = RadioSet('Quanta', 'Generation', 'Identity')
            self.style_property.border_title = 'Style Property'
            yield self.style_property

            # general controls
            self.render_controls = SelectionList(
                *(Selection(*c) for c in self._render_controls),
                id='render-controls'
            )
            self.render_controls.border_title = 'Render Controls'
            yield self.render_controls

            # highlight controls
            self.highlight_generations = Input(placeholder='1, 2: bold; a: red', id='highlight-gens')
            self.highlight_generations.border_title = 'Highlight Generations'
            yield self.highlight_generations
            self.highlight_ids = Input(placeholder='a, b: red; 3: blue', id='highlight-ids')
            self.highlight_ids.border_title = 'Highlight IDs'
            yield self.highlight_ids

            # overrides
            self.style_map = Input("auto", placeholder='1, a: red; 2, b: blue', id='style-map')
            self.style_map.border_title = 'Style Override'
            yield self.style_map
            self.symbol_map = Input("auto", placeholder='1, a: X; 2: Y', id='symbol-map')
            self.symbol_map.border_title = 'Symbol Map'
            yield self.symbol_map

            yield Button('↻ Cache Refresh', id='refresh-cache')

        with Collapsible(title='Hover Explorer', collapsed=False):
            self.hover_active_ruleset = Checkbox('Hover Active Ruleset', id='hover-active-ruleset')
            yield self.hover_active_ruleset

            self.hovered_info_label = Label()
            self._reset_hovered_info_label()
            yield self.hovered_info_label

            self.id_hover = Checkbox('Highlight Identity', id='id-hover')
            yield self.id_hover
            self.id_hover_style = Input("on yellow", placeholder='e.g. on red or bold blue', id='id-hover-style')
            self.id_hover_style.border_title = 'Identity Style'
            yield self.id_hover_style

            self.gen_hover = Checkbox('Highlight Generation', id='gen-hover')
            yield self.gen_hover
            self.gen_hover_style = Input("on blue", placeholder='e.g. on red or bold blue', id='gen-hover-style')
            self.gen_hover_style.border_title = 'Generation Style'
            yield self.gen_hover_style

        yield Label()

    def handle_input_submit(self, e: Input.Submitted):
        _id: str | None = e.input.id
        if _id == 'render-range':
            try:
                rs: list[str] = e.value.strip().split(':')
                if len(rs) == 2: rs.append('')  # it must always be 3 things
                self._render_range = (  # type: ignore
                    int(rs[0]) if rs[0] else 0,
                    str_to_num(rs[1]) if rs[1] else INF,
                    abs(int(rs[2])) if rs[2] else 1
                )
                self._rebuild_rows()
            except:
                self.view.notify('Invalid render range.', severity='warning')
                e.input.value = '{0}:{1}:{2}'.format(*self._render_range)

        elif _id in ('style-map', 'symbol-map'):
            self._handle_styling_update()

        elif _id == 'hover-style':
            self.space_formatter.high = e.value.strip()

    def handle_selection_toggle(self, e: SelectionList.SelectionToggled):
        _id: str = e.selection_list.id
        if _id == 'column-controls':
            self._render_control_bitmap_zero_out()
            for i in e.selection_list.selected:
                self._enabled_columns[i] = True
            self._rebuild_columns()
        if _id == 'render-controls':
            self._handle_styling_update()

    def handle_checkbox_change(self, e: Checkbox.Changed):
        _id: str | None = e.checkbox.id
        if _id == 'hover-explorer':
            self.data_table.enabled_sig_mouse_over_space_cell = e.value  # type: ignore
            self.hover_active_ruleset.disabled = not e.value
            if not e.value:
                self.hover_active_ruleset.value = self.hovered_ruleset_container.display = False
                self._reset_hovered_info_label()
                self._cell_ids_to_highlight = frozenset()
        if _id == 'hover-active-ruleset' and self.hover_active_ruleset.value:
            self.hovered_ruleset_container.display = e.value
            if not e.value:
                self.active_ruleset_table.clear()
        if _id == 'show-ruleset':
            self.ruleset_container.display = e.value

    def panel(self) -> TabPane | None:
        # Ruleset Table
        self.ruleset_table = _DataTable(id='ruleset-table', show_cursor=False)
        self.ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.ruleset_container = Vertical(
            Label('[bold] Ruleset Table [/bold]'),
            self.ruleset_table
        )

        # Ruleset Table
        self.active_ruleset_table = _DataTable(id='active-ruleset-table', show_cursor=False)
        self.active_ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.hovered_ruleset_container = Vertical(
            Label('[bold] Active Ruleset Table [/bold]'),
            self.active_ruleset_table,
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
        for i in self.render_controls.selected:
            control_bitmap[i] = True
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

        self.space_formatter.config(
            *control_bitmap[:4],
            style_map,
            control_bitmap[4],
            symbol_map
        )

        self._rebuild_ruleset_table(self.flow.ruleset.rules, self.ruleset_table)
        self._rebuild_rows()

    def _reset_hovered_info_label(self):
        self.hovered_info_label.content = """[bold]Cell Info[/bold]
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
        flow: FlowLang = self.flow
        event: FlowEvent = flow.events[row_idx]
        spaces: tuple[tuple[DeltaSpaces, DeltaSpace, SpaceState], ...] = tuple(event.spaces_with_metadata)
        space_state: SpaceState = spaces[column_idx][2]

        # update the rows
        if offset >= len(space_state):
            reset_highlighted()
            return
        flow_cell: FlowCell = space_state.get_all_cells()[offset]
        self._cell_ids_to_highlight = frozenset((flow_cell.id,))
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
            lifespan: int = cell_destroyed_at - flow_cell.generation
        except IndexError:
            cell_destroyed_at: None = None
            lifespan: None = None
        connected_events = tuple(event.causally_connected_events)
        self.hovered_info_label.content = f"""[bold]Cell #{offset}[/bold]
• Encoded: {flow_cell.quanta}
• Quanta: {flow_cell.quanta}
• Generation: {flow_cell.generation}
• Identity: {flow_cell.id}
"""

        # place the rule (and its chain if there is one) in the hovered ruleset table.
        if self.hover_ruleset_enabled.value:
            applied_rule: BaseRule = spaces[column_idx][0].rule
            if applied_rule:
                self._rebuild_ruleset_table(applied_rule.chain, self.active_ruleset_table, hide_disabled=True, remember_old_row_length=True)

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
                    selectors.append(self.space_formatter.convert_pure_str(sv))
                else:
                    selectors.append(Text(str(sv)))
            targets: list[Text] = []
            for t in rule.target:
                tv = t.target
                if isinstance(tv, int):
                    targets.append(Text(str(tv)))
                else:  # when `tv` is Sequence[int]
                    targets.append(self.space_formatter.convert_pure_str(''.join(str(c) for c in tv)))
            return (Text(', ').join(selectors) if len(selectors) > 1 else selectors[0] if selectors else '',  # type: ignore
                    Text(', ').join(targets) if len(targets) > 1 else targets[0] if targets else '')

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

    def on_evolved(self, steps: int) -> None:
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
            for event in self.flow.events[-steps:]:
                if short_circuit or flush_mode and dt.row_count >= render_limit:
                    short_circuit = True
                    cft(lambda: dt.remove_row(dt.coordinate_to_cell_key(Coordinate(0, 0)).row_key))
                cft(self._add_row, event)
        cft(self._refresh_column_widths)
        if not flush_mode:
            dt.scroll_end(animate=False)

    def on_undo(self, steps: int) -> None:
        # NOTE: this function is not very optimized for updates, but premature optimization is the root of all evil.
        cft = self.cft
        dt = self.data_table
        old_rows_count = len(self.flow.events) + steps
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
        control_bitmap = self._enabled_columns
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
        formatter: SpaceState1DFormatter = self.space_formatter
        cells_to_highlight: frozenset[int] = self._cell_ids_to_highlight
        for i in range(self._raw_space_columns_limit):
            try:
                space = spaces.__next__()  # we must always increment next (even though it may be hidden, that is what makes the check work)
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
        for event in self.flow.events[a:b + (1 if b > 0 else 0):c]:
            self._add_row(event)
        self._refresh_column_widths()
        dt.scroll_to(x=old_x, y=old_y, animate=False)

    def _rebuild_columns(self, rebuild_rows: bool = True) -> None:
        dt = self.data_table
        old_x, old_y = dt.scroll_x, dt.scroll_y
        dt.clear(columns=True)
        if self._enabled_columns[0]:
            dt.add_column('Event', key='event')
        if self._enabled_columns[1]:
            dt.add_column('Distance', key='distance')
        if self._enabled_columns[2]:
            dt.add_column('Connected', key='connected')
        for i in range(self._raw_space_columns_limit):
            dt.add_column(_:=str(i), key=_)
        if rebuild_rows:
            self._rebuild_rows()
        dt.scroll_to(x=old_x, y=old_y, animate=False)

    def _refresh_column_widths(self) -> None:
        """Update the column widths as Textual does not currently do that for us when removing rows."""
        dt = self.data_table
        if 0 <= (rc:=(dt.row_count - 1)):
            # noinspection protected-member
            dt._update_column_widths(
                {dt.coordinate_to_cell_key(Coordinate(rc, i)) for i in range(len(dt.columns))}
            )
