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
from textual.widgets import (Collapsible, Button, TabPane, Input, Checkbox, Label, DataTable as _DataTable, SelectionList, RadioSet, RadioButton)
from textual.widgets.data_table import CellKey
from textual.widget import Widget
from textual.coordinate import Coordinate
from textual.widgets.selection_list import Selection
from textual.containers import VerticalScroll, Horizontal, Vertical
from textual.events import MouseMove

# Standard Imports
from typing import Iterator, Sequence
from core.engine import Event as FlowEvent, Cell as FlowCell, DeltaCell, DeltaSpace, Coordinate as SpaceCoordinate
from core.topologies.nd_space import SpaceState1D as SpaceState
from core.topologies.tooling.prettier import SpaceState1DFormatter
from core.topologies.tooling.rff_encoding import ord_rff, chr_rff
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
        self._event_range: slice = slice(-100, None)  # this is inclusive to both ends
        self._space_coordinate: SpaceCoordinate = SpaceCoordinate(-1, 0)
        self._hover_highlight_cells_with_id: dict[int, str] = {}
        self._hover_highlight_cells_in_generation: dict[int, str] = {}
        self._columns_controls = (  # (control title, column title, is actual column, control key, default value)
            ("Cell Count", 'Cells', True, 'cell-count', False),
            ("Causal Distance", 'Distance', True, 'causal-distance', False),
            ("Causally Connected", 'Connected', True, 'causally-connected', False),
            ("├─ Show List", None, False, 'causal-list', False),
            ("│  ╰─ Sorted", None, False, 'sorted-causal-list', False),
            ("╰─ Unique Set", None, False, 'unique-causal-list', False),
            ("Destroyed Cells", 'Destroyed', True, 'destroyed-cells', False),
            ("Created Cells", 'Created', True, 'created-cells', False),
            ("Space Count", 'Space #', True, 'space-count', False),
            ("Show Space", 'Space', True, 'space', True)
        )
        self._render_controls = (  # (control title, control key, default value)
            ("Cell Styling", 'cell-styling', True),
            ("├─ On Background", 'cell-styling-on-background', True),
            ("╰─ Exclusive Mapping", 'exclusive-mapping', False),
            ("Show Symbols", 'show-symbols', True),
            ("╰─ Encode Ordinals", 'show-encoded-symbols', True),
        )
        self._render_controls_hash: int = 0  # used to only refresh the cash if something actually changed.

        # connect model signals
        self.flow.on_evolved_n.connect(lambda: self.cft(self._rebuild_rows))
        self.flow.on_regress_n.connect(lambda: self.cft(self._rebuild_rows))
        self.flow.on_clear.connect(self.hande_flow_clear)
        self.flow.on_ruleset_set.connect(
            lambda: self.cft(self._rebuild_ruleset_table, self.flow.ruleset.rules, self.ruleset_table)
        )

        # connect view signals
        self.view.sig_input_submit.connect(self.handle_input_submit)
        self.view.sig_selection_list_toggled.connect(self.handle_selection_toggle)
        self.view.sig_radio_set_changed.connect(self.handle_radio_set_change)
        self.view.sig_checkbox_changed.connect(self.handle_checkbox_change)
        self.view.sig_button_pressed.connect(self.handle_button_press)

        # temp trackers
        self.__last_hover_coord_and_offset: tuple[Coordinate, int] = (Coordinate(0, 0), 0)

    def get_flow_events(self) -> Iterator[tuple[SpaceState, FlowEvent]]:
        """Gets the SpaceState and the associated event given the current space coordinate and event range.

        FUTURE:
        - This needs to be optimized for minimal walk steps.
        """
        event_coord: int = self._space_coordinate.event_idx
        if event_coord < 0:
            event_coord: int = len(self.flow.events) + event_coord
        events: list[FlowEvent] = self.flow.events[:event_coord + 1][self._event_range]
        if self.walk_branch.value:
            walker: Iterator[SpaceState] = self.flow.walk_branch(  # type: ignore
                self._space_coordinate
            )
            spaces: list[SpaceState] = list(walker)
            spaces.reverse()
            yield from zip(spaces[self._event_range], events)
        else:
            space_coord: int = self._space_coordinate.space_idx
            for event in events:
                i: Iterator[SpaceState] = event.spaces  # type: ignore
                space: SpaceState = next(i)
                if space_coord > 0:
                    try:
                        for _ in range(space_coord - 1):
                            space = next(i)
                    except StopIteration: pass
                yield space, event

    def controls(self) -> Iterator[Widget]:
        self.event_range = Input(value='-100:', placeholder='e.g. -10: or 3:10', id='event-range')
        self.event_range.border_title = 'Event Range'
        yield self.event_range

        self.space_coordinate = Input(str(self._space_coordinate), placeholder='e.g. (4, 2)', id='space-coordinate')  # (FUTURE SUPPORT FOR MULTIPLE SPACE COLUMNS)
        self.space_coordinate.border_title = 'Space Coordinate'
        yield self.space_coordinate

        self.walk_branch = Checkbox('Ensure Branch Integrity', value=True, id='walk-branch')
        self.walk_branch.value = False
        self.walk_branch.tooltip = 'Walk up the multi-way tree nodes to ensure that the temporal relationship between spaces is conserved (as opposed to trusting that no branches have terminated).'
        yield self.walk_branch

        with Collapsible(title='Table Controls', collapsed=False):
            self.data_table_controls = SelectionList(
                *(Selection(c[0], c[3], c[4]) for c in self._columns_controls),
                id='data-table-controls'
            )
            self.data_table_controls.border_title = 'Data Table'
            self._rebuild_columns(rebuild_rows=False)  # must be called here or sometime after to initiate columns.
            yield self.data_table_controls

            self.show_ruleset = Checkbox('Show Ruleset', value=True, id='show-ruleset')
            self.show_ruleset.value = False
            yield self.show_ruleset

        with Collapsible(title='Cell Rendering', collapsed=False):
            # color palette
            with Collapsible(title='Color Palette', collapsed=False):
                self.ordered_color_palette = Checkbox('Ordered Spectrum', value=True, id='ordered-color-palette')
                self.ordered_color_palette.value = False
                yield self.ordered_color_palette

                self.color_palette = Input(str(self.space_formatter.color_palette_seed), type='integer', id='color-palette')
                self.color_palette.border_title = 'Color Palette'
                yield self.color_palette

                self.default_char_color = Input(str(self.space_formatter.default_char_color), id='default-char-color')
                self.default_char_color.border_title = 'Default Char Color'
                yield self.default_char_color

            self.cell_width = Input('3', type='integer', id='cell-width')
            self.cell_width.border_title = 'Cell Width'
            yield self.cell_width

            # property based controls
            with RadioSet(id='encode-property') as r:
                self.encode_property = r
                self.encode_property.border_title = 'Encode Property'
                yield RadioButton('Quanta', value=True)
                yield RadioButton('Generation')
                yield RadioButton('Identity')
            with RadioSet(id='style-property') as r:
                self.style_property = r
                self.style_property.border_title = 'Style Property'
                yield RadioButton('Quanta', value=True)
                yield RadioButton('Generation')
                yield RadioButton('Identity')

            # general controls
            self.render_controls = SelectionList(
                *(Selection(*c) for c in self._render_controls),
                id='render-controls'
            )
            self.render_controls.border_title = 'Render Controls'
            yield self.render_controls

            # highlight controls
            self.highlight_generations = Input('None', placeholder='1, 2: bold; "a": red', id='highlight-gens')
            self.highlight_generations.border_title = 'Highlight Generations'
            yield self.highlight_generations
            self.highlight_ids = Input('None', placeholder='"a", "b": red; 3: blue', id='highlight-ids')
            self.highlight_ids.border_title = 'Highlight IDs'
            yield self.highlight_ids

            # overrides
            self.style_map = Input('None', placeholder='4, "a": blue; "b": red', id='style-map')
            self.style_map.border_title = 'Style Map'
            yield self.style_map
            self.symbol_map = Input('None', placeholder='5, "a": 65; 2: "Y"', id='symbol-map')
            self.symbol_map.border_title = 'Symbol Map'
            yield self.symbol_map

            yield Button('↻ Refresh Cache', id='refresh-cache')

        with Collapsible(title='Hover Explorer', collapsed=False):
            self.show_active_ruleset = Checkbox('Show Active Ruleset', id='show-active-ruleset')
            yield self.show_active_ruleset

            self.show_hovered_cell_info = Checkbox('Show cell info', id='show-hovered-cell-info')
            yield self.show_hovered_cell_info

            self.hovered_info_label = Label()
            self.hovered_info_label.display = False
            self._reset_hovered_info_label()
            yield self.hovered_info_label

            self.id_hover = Checkbox('Highlight Identity', id='id-hover')
            yield self.id_hover
            self.id_hover_style = Input("on yellow", placeholder='e.g. on red or bold blue', disabled=True, id='id-hover-style')
            self.id_hover_style.border_title = 'Identity Style'
            yield self.id_hover_style

            self.gen_hover = Checkbox('Highlight Generation', id='gen-hover')
            yield self.gen_hover
            self.gen_hover_style = Input("on blue", placeholder='e.g. on red or bold blue', disabled=True, id='gen-hover-style')
            self.gen_hover_style.border_title = 'Generation Style'
            yield self.gen_hover_style

        yield Label()

    def panel(self) -> TabPane | None:
        # Ruleset Table
        self.ruleset_table = _DataTable(id='ruleset-table', show_cursor=False)
        self.ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.ruleset_container = Vertical(
            Label('[bold] Ruleset Table [/bold]'),
            self.ruleset_table
        )
        self.ruleset_container.display = False

        # Ruleset Table
        self.active_ruleset_table = _DataTable(id='active-ruleset-table', show_cursor=False)
        self.active_ruleset_table.add_columns('Selector', 'Target', 'Type', 'Group')
        self.active_ruleset_container = Vertical(
            Label('[bold] Active Ruleset Table [/bold]'),
            self.active_ruleset_table,
        )
        self.active_ruleset_container.display = False

        # Evolution Table
        self.data_table_label = Label('[bold] Data Table [/bold]')
        self.data_table = DataTable(id='data-table')
        self.data_table.sig_mouse_over_inner_cell.connect(self._handle_mouse_over_data_table)
        return TabPane(
            self.name.title(),
            RulesetDashboard(
                Horizontal(
                    self.ruleset_container,
                    self.active_ruleset_container
                ),
                self.data_table_label,
                self.data_table
            )
        )

    def handle_input_submit(self, e: Input.Submitted):
        _id: str | None = e.input.id
        if _id == 'event-range':
            try:
                sr: list[str] = e.value.strip().split(':')
                a: int | None = int(sr[0]) if sr[0] else None
                b: int | None = int(sr[1]) if sr[1] else None
                self._event_range = slice(a, b)
                self._rebuild_rows()
            except:
                self.view.notify('Invalid event range.', severity='warning')
                oa, ob = self._event_range.start, self._event_range.stop
                e.input.value = f'{"" if oa is None else oa}:{"" if ob is None else ob}'

        elif _id == 'space-coordinate':
            try:
                coord: SpaceCoordinate = eval(f't{e.value.strip()}', globals={'t': SpaceCoordinate})
                if not isinstance(coord, SpaceCoordinate):
                    raise Exception
                self._space_coordinate = coord
                self._rebuild_rows()
            except:
                self.view.notify('Invalid space coordinate.', severity='warning')
                e.input.value = '({}, {})'.format(*self._space_coordinate)

        elif _id in ('cell-width', 'color-palette', 'default-char-color', 'highlight-gens', 'highlight-ids', 'style-map', 'symbol-map'):
            self._handle_styling_update()

    def handle_selection_toggle(self, e: SelectionList.SelectionToggled):
        _id: str = e.selection_list.id
        if _id == 'data-table-controls':
            table_enabled: bool = bool(len(e.selection_list.selected))
            self.data_table_label.display = table_enabled
            self.data_table.display = table_enabled
            self.event_range.disabled = not table_enabled
            self.space_coordinate.disabled = not table_enabled
            self._rebuild_columns()
        elif _id == 'render-controls':
            self._handle_styling_update()

    def handle_radio_set_change(self, e: RadioSet.Changed):
        _id: str | None = e.radio_set.id
        if _id in ('encode-property', 'style-property'):
            self._handle_styling_update()

    def handle_checkbox_change(self, e: Checkbox.Changed):
        _id: str | None = e.checkbox.id
        if _id == 'show-ruleset':
            self.ruleset_container.display = e.value
        elif _id == 'ordered-color-palette':
            self.color_palette.disabled = bool(e.value)
            self._handle_styling_update()
        elif _id == 'show-active-ruleset':
            self.active_ruleset_container.display = e.value
            if not e.value:
                self.active_ruleset_table.clear()
        elif _id == 'show-hovered-cell-info':
            self.hovered_info_label.display = bool(e.value)
        elif _id == 'id-hover':
            self.id_hover_style.disabled = not bool(e.value)
        elif _id == 'gen-hover':
            self.gen_hover_style.disabled = not bool(e.value)

    def handle_button_press(self, e: Button.Pressed):
        _id: str | None = e.button.id
        if _id == 'refresh-cache':
            self.space_formatter.reset_cache()
            self._handle_styling_update()

    def hande_flow_clear(self):
        try:
            self.cft(self.data_table.clear)
        except RuntimeError:  # this function may or may not be called within the main thread.
            self.data_table.clear()

    @staticmethod
    def parse_character_key_values(data: str) -> dict:
        result = {}
        pairs = data.split(';')
        for pair in pairs:
            pair = pair.strip()
            if not pair or ':' not in pair:
                continue

            left_side, right_side = pair.split(':', 1)
            left_side = left_side.strip()
            right_side = right_side.strip()

            # ==== Process the Value ====
            if right_side.startswith('"') and right_side.endswith('"'):
                parsed_val = right_side[1:-1]
            else:
                try:
                    parsed_val = chr_rff(int(right_side))
                except ValueError:
                    parsed_val = right_side

            # ==== Process the Keys ====
            keys = left_side.split(',')
            for k in keys:
                k = k.strip()
                if not k:
                    continue
                if k.startswith('"') and k.endswith('"'):
                    try:
                        parsed_key = ord_rff(k[1:-1])
                    except TypeError:
                        continue
                else:
                    try:
                        parsed_key = int(k)
                    except ValueError:
                        try:
                            parsed_key = ord_rff(k)
                        except TypeError:
                            continue
                result[parsed_key] = parsed_val

        return result

    def _handle_styling_update(self):
        formatter: SpaceState1DFormatter = self.space_formatter

        # ==== Set fragile controls (controls that require cache refresh) ====
        fragile_controls_hash: int = hash(
            (
                self.cell_width.value,
                tuple(self.render_controls.selected),
                self.ordered_color_palette.value,
                self.color_palette.value,
                self.default_char_color.value,
                self.style_map.value,
                self.symbol_map.value
            )
        )
        if fragile_controls_hash != self._render_controls_hash:
            # Set the cell width
            formatter.cell_width = int(self.cell_width.value)
            selected_render_controls = set(self.render_controls.selected)

            # Set the render controls
            render_controls_bitmap: dict[str, bool] = {
                c[1]: c[1] in selected_render_controls
                for c in self._render_controls
            }
            formatter.styling = render_controls_bitmap['cell-styling']
            formatter.style_on_background = render_controls_bitmap['cell-styling-on-background']
            formatter.clear_default_styles_on_override = render_controls_bitmap['exclusive-mapping']
            formatter.show_symbols = render_controls_bitmap['show-symbols']
            formatter.encode_ordinals = render_controls_bitmap['show-encoded-symbols']

            # Set the color palette
            if self.color_palette.value and not self.ordered_color_palette.value:
                formatter.set_color_palette_seed(int(self.color_palette.value))
            else:
                formatter.set_color_palette_seed(None)
            formatter.default_char_color = self.default_char_color.value

            # Set the overrides
            if self.style_map.value != 'None':
                formatter.style_mapping_override = self.parse_character_key_values(self.style_map.value)
            if self.symbol_map.value != 'None':
                formatter.symbol_mapping_override = self.parse_character_key_values(self.symbol_map.value)

            # Reset the cache and set new hash
            self.space_formatter.reset_cache()
            self._render_controls_hash = fragile_controls_hash

        # ==== Set persistent controls (no cache refresh needed) ====
        # Ordinal Properties
        formatter.encode_using_property = self.encode_property.pressed_index
        formatter.style_using_property = self.style_property.pressed_index

        # Highlighters
        if self.highlight_generations.value != 'None':
            formatter.highlight_cells_in_generation = self.parse_character_key_values(self.highlight_generations.value)
        if self.highlight_ids.value != 'None':
            formatter.highlight_cells_with_id = self.parse_character_key_values(self.highlight_ids.value)

        # Rebuild the data table and the ruleset table
        self._rebuild_ruleset_table(self.flow.ruleset.rules, self.ruleset_table)  # type: ignore
        self._rebuild_rows()

    def _reset_hovered_info_label(self):
        self.hovered_info_label.content = """
[bold]Cell Info[/bold]
• ----
• ----
• ----
• ----
"""

    # TODO: we need to get the ECA working again...
    def _reset_temp_highlighted_cells(self):
        self._reset_hovered_info_label()
        if self._cell_ids_to_highlight:
            self._cell_ids_to_highlight = frozenset()
            self._rebuild_rows()

    def _handle_mouse_over_data_table(self, coord: Coordinate | None, offset: int) -> None:
        return
        if (not coord
                or offset == -1
                or self.data_table.coordinate_to_cell_key(coord).column_key in ('event', 'distance', 'connected')):
            self._reset_temp_highlighted_cells()
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
        spaces: tuple[tuple[DeltaSpace, SpaceState], ...] = tuple(event.spaces_with_deltas)
        space_state: SpaceState = spaces[column_idx][2]

        # update the rows
        if offset >= len(space_state):
            self._reset_temp_highlighted_cells()
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
        self.hovered_info_label.content = f"""
[bold]Cell #{offset}[/bold]
• Encoded: {flow_cell.quanta}
• Quanta: {flow_cell.quanta}
• Generation: {flow_cell.generation}
• Identity: {flow_cell.id}
"""

        # place the rule (and its chain if there is one) in the hovered ruleset table.
        if self.hover_ruleset_enabled.value:
            applied_rule: BaseRule = spaces[column_idx][0].rule
            if applied_rule:
                self._rebuild_ruleset_table(applied_rule.chain, self.active_ruleset_table, hide_disabled=True, remember_old_row_count=True)

    def _rebuild_ruleset_table(self, rules: Sequence[BaseRule],
                               table: DataTable,
                               hide_disabled: bool = False,
                               remember_old_row_count: bool = False) -> None:
        # TODO: add dedicated controls for the ruleset table such as showing type, Group, hiding disabled, etc.
        def print_rule(rule: BaseRule) -> tuple[Text, Text]:
            selectors: list[Text] = []
            for s in rule.selector:
                if s.type == 'literal':
                    selectors.append(self.space_formatter.convert_pure_sequence(s.selector))  # type: ignore
                elif s.type == 'regex':
                    selectors.append(Text('Re:') + self.space_formatter.convert_pure_sequence(s.selector))  # type: ignore
                else:
                    selectors.append(Text(str(s.selector)))
            targets: list[Text] = []
            for t in rule.target:
                if t.type == 'literal':
                    targets.append(self.space_formatter.convert_pure_sequence(t.target))  # type: ignore
                else:  # when `tv` is Sequence[int]
                    targets.append(Text(str(t.target)))
            return (Text(', ').join(selectors) if len(selectors) > 1 else selectors[0] if selectors else '',  # type: ignore
                    Text(', ').join(targets) if len(targets) > 1 else targets[0] if targets else '')

        table.clear()
        rule: BaseRule
        for i, rule in enumerate(rules):
            if hide_disabled and rule.disabled:
                continue
            table.add_row(
                *print_rule(rule), rule.__class__.__name__, rule.group,
                label=str(i)
            )

        old_row_count: int = table.row_count
        if remember_old_row_count and table.row_count < old_row_count:
            for _ in range(old_row_count - table.row_count): table.add_row()

    def _add_row(self,space_state: SpaceState,
                 event: FlowEvent,
                 column_bitmap: list[bool],
                 column_modifiers: list[bool]) -> None:
        columns = []

        # Process the info columns
        causally_connected: int = 0
        if column_bitmap[2]:
            if column_modifiers[2]:  # if we are collapsing it
                causally_connected: set[int] = set(event.causally_connected_events)
            else:
                causally_connected: Sequence[int] = tuple(event.causally_connected_events)
            if column_modifiers[0]:
                if column_modifiers[1]:
                    causally_connected: Sequence[int] = sorted(causally_connected)
                # nothing needs to happen as we already have the list
            else:
                causally_connected: int = len(causally_connected)  # default

        destroyed_cells: int = 0
        created_cells: int = 0
        if column_bitmap[3] or column_bitmap[4]:
            for dc in event.affected_cells:
                destroyed_cells += len(dc.destroyed_cells)
                created_cells += len(dc.new_cells)

        space_count: int = 0
        if column_bitmap[5]:
            for _ in event.spaces:
                space_count += 1

        renderable_space: None = None
        if column_bitmap[6]:
            renderable_space: Text = self.space_formatter(space_state)

        for data, visible in zip(
                (
                        len(space_state.vec),
                        event.causal_distance_to_creation,
                        causally_connected,
                        destroyed_cells,
                        created_cells,
                        space_count,
                        renderable_space
                ),
                column_bitmap
        ):
            if visible:
                columns.append(data)

        # Add everything as a row
        time: str = str(event.time)
        self.data_table.add_row(
            *columns,
            key=time,
            label=time
        )

    def _rebuild_rows(self) -> None:
        dt = self.data_table
        old_x, old_y = dt.scroll_x, dt.scroll_y
        dt.clear()

        column_bitmap: list[bool] = []
        column_modifiers: list[bool] = []
        selected_column_controls = set(self.data_table_controls.selected)
        for control_title, column_title, is_column, control_key, default_value in self._columns_controls:
            (column_bitmap if is_column else column_modifiers).append(control_key in selected_column_controls)
        for t in self.get_flow_events():
            self._add_row(*t, column_bitmap, column_modifiers)

        self._refresh_column_widths()
        dt.scroll_to(x=old_x, y=old_y, animate=False)

    def _rebuild_columns(self, rebuild_rows: bool = True) -> None:
        dt = self.data_table
        old_x, old_y = dt.scroll_x, dt.scroll_y
        dt.clear(columns=True)

        # build columns
        selected_column_controls = set(self.data_table_controls.selected)
        for control_title, column_title, is_column, control_key, default_value in self._columns_controls:
            if control_key not in selected_column_controls or not is_column:
                continue
            if not column_title:
                column_title = ''
            dt.add_column(column_title, key=control_key)

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
