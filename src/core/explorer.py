"""
explorer.py

Rich-based visualization wrapper for the Flow engine.
Designed to be agnostic between CLI (Rich Console) and TUI (Textual) environments.
"""

from typing import Any, Optional, Dict, Iterator, List
from rich.console import Console, Style
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich import box
from rich.color import Color

# Handle import based on your structure
from src.core.engine import Flow, Event, Cell



class StyleManager:
    """
    Manages the mapping between Cell quanta and Rich styles.
    """

    def __init__(self, custom_map: Optional[Dict[Any, str]] = None):
        # Default colors (backgrounds used to support both text and block modes)
        Style()
        self._color_map: Dict[Any, str] = custom_map or {
            'A': "bold white on red",
            'B': "bold white on green",
            'C': "bold white on blue",
        }

        # A palette of background styles for auto-assignment
        self._palette = [
            "on cyan", "on magenta", "on yellow", "on bright_black",
            "on bright_red", "on bright_green", "on bright_blue"
        ]
        self._ptr = 0

    def register(self, quanta: Any, style: str) -> None:
        """Manually register a style."""
        self._color_map[quanta] = style

    def get_style(self, quanta: Any) -> str:
        """Get style for quanta, assigning a new one from palette if unseen."""
        key = str(quanta)
        if key not in self._color_map:
            # Assign next color in palette
            style = self._palette[self._ptr % len(self._palette)]
            self._color_map[key] = style
            self._ptr += 1
        return self._color_map[key]


class FlowExplorerRich:
    """
    Visualization engine for Flow.
    """
    def __init__(self,
                 flow: Flow,
                 console: Optional[Console] = None,
                 block_mode: bool = False):
        """
        Args:
            flow: The simulation engine instance.
            console: Optional Rich console (created automatically if None).
            block_mode: If True, renders cells as empty colored squares (2 spaces).
        """
        self.flow = flow
        self.console = console or Console(force_terminal=True)
        self.styler = StyleManager()
        self.block_mode = block_mode
        self._table: Optional[Table] = None

    def _render_cell(self, cell: Cell) -> Text:
        """
        Renders a single cell.
        """
        style = self.styler.get_style(cell.quanta)

        if self.block_mode:
            return Text("  ", style=style)
        else:
            return Text(f" {cell.quanta} ", style=style)

    def _render_space(self, space_state) -> Text:
        """Renders a full space (line of cells)."""
        text_builder = Text()
        cells = getattr(space_state, 'cells', space_state)
        for cell in cells:
            text_builder.append(self._render_cell(cell))
        return text_builder

    def _setup_table_structure(self,
                               title: Optional[str] = None,
                               box_style: box.Box = box.ROUNDED,
                               show_header: bool = True,
                               padding: tuple[int, int] = (0, 1),
                               show_idx: bool = True,
                               show_causal_dist: bool = False,
                               show_connected: bool = False) -> Table:
        """
        Creates the empty table definition with customizable visuals.
        """
        table = Table(
            title=title,
            box=box_style,
            show_header=show_header,
            show_edge=True,
            padding=padding,
            collapse_padding=True,
            pad_edge=False
        )

        if show_idx:
            table.add_column("Idx", justify="right", style="dim", no_wrap=True)

        table.add_column("State", ratio=1)

        if show_causal_dist:
            table.add_column("Dist", justify="center", style="italic")

        if show_connected:
            table.add_column("Causes", style="dim", overflow="fold")

        return table

    def render_event_row(self,
                         idx: int,
                         event: Event,
                         show_idx: bool = True,
                         show_causal_dist: bool = False,
                         show_connected: bool = False) -> List[Any]:
        """
        Generates the raw data for a single row.
        """
        row_data = []
        if show_idx:
            row_data.append(str(idx))

        try:
            spaces = list(event.spaces) if isinstance(event.spaces, Iterator) else event.spaces
        except TypeError:
            spaces = [event.spaces]

        rendered_spaces = [self._render_space(s) for s in spaces]

        if len(rendered_spaces) == 1:
            row_data.append(rendered_spaces[0])
        else:
            row_data.append(Text("\n").join(rendered_spaces))

        if show_causal_dist:
            dist = getattr(event, 'causal_distance_to_creation', '-')
            row_data.append(str(dist))

        if show_connected:
            conn = getattr(event, 'causally_connected_events', [])
            row_data.append(str(set(conn)) if conn else "-")

        return row_data

    def get_table(self,
                  title: Optional[str] = None,
                  box_style: box.Box = box.ROUNDED,
                  show_header: bool = True,
                  show_idx: bool = True,
                  show_causal_dist: bool = False,
                  show_connected: bool = False) -> Table:
        """
        Returns a fully populated Rich Table.
        """
        table = self._setup_table_structure(
            title=title,
            box_style=box_style,
            show_header=show_header,
            show_idx=show_idx,
            show_causal_dist=show_causal_dist,
            show_connected=show_connected
        )

        for i, event in enumerate(self.flow.events):
            row_data = self.render_event_row(i, event, show_idx, show_causal_dist, show_connected)
            table.add_row(*row_data)

        return table

    def explore(self,
                show_idx: bool = True,
                show_causal_dist: bool = False,
                show_connected: bool = False,
                title: Optional[str] = None,
                box_style: box.Box = box.ROUNDED,
                live: bool = False,
                refresh_rate: float = 4.0):
        """
        CLI Entry point.
        """
        self._table = self._setup_table_structure(
            title=title,
            box_style=box_style,
            show_idx=show_idx,
            show_causal_dist=show_causal_dist,
            show_connected=show_connected
        )

        def add_rows_to_table():
            current_row_count = self._table.row_count
            total_events = len(self.flow.events)

            for i in range(current_row_count, total_events):
                event = self.flow.events[i]
                row = self.render_event_row(i, event, show_idx, show_causal_dist, show_connected)
                self._table.add_row(*row)

        if not live:
            add_rows_to_table()
            self.console.print(self._table)
        else:
            with Live(self._table, console=self.console, refresh_per_second=refresh_rate) as live_view:
                self._table = self._setup_table_structure(title, box_style, True, (0,1), show_idx, show_causal_dist, show_connected)
                live_view.update(self._table)

                for i, event in enumerate(self.flow.events):
                    row = self.render_event_row(i, event, show_idx, show_causal_dist, show_connected)
                    self._table.add_row(*row)


class FlowExplorerTextual:
    pass


if __name__ == "__main__":
    from src.implementations.sss import SSS

    # 1. Run your simulation
    system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space='A')
    system.evolve_n(10)

    # 2. Visualize
    viz = FlowExplorerRich(system, block_mode=False)

    # Optional: Custom colors (defaults are Red for A, Green for B)
    # viz.set_color('A', 'bold red on red')
    # viz.set_color('B', 'bold green on green')

    # 3. Render
    viz.explore(
        show_idx=True,
        show_causal_dist=True,
        show_connected=True
    )
