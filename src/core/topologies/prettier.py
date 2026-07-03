"""
prettier.py
Rich-based visualization wrapper for the Flow engine's SpaceState.

TODO:
- Add options for Nd rendering.
"""
from string import ascii_uppercase, ascii_lowercase, digits
from typing import Iterator, Sequence
from rich.text import Text
from core.topologies.nd_space import SpaceState1D


COLOR_PALETTE: list[str] = [
    '#1a4e8b', '#8b0000', '#2d8b2d', '#8b1a72', '#00728b', '#8b5e1a', '#4e1a8b', '#6b8b1a', '#8b1a43', '#1a7e8b',
    '#7b8b1a', '#5c1a8b', '#1a8b43', '#8b431a', '#1a2d8b', '#8b7b1a', '#8b1a62', '#1a8b7e', '#3c1a8b', '#3d8b1a',
    '#8b221a', '#1a5c8b', '#1a8b22', '#6e1a8b', '#5a8b1a', '#8b1a82', '#1a8b51', '#8b691a', '#2d1a8b', '#4e8b1a',
    '#8b1a33', '#1a788b', '#7e8b1a', '#471a8b', '#1a8b34', '#8b3d1a', '#1a3d8b', '#628b1a', '#8b1a6e', '#1a648b',
    '#758b1a', '#221a8b', '#1a8b4e', '#8b511a', '#348b1a', '#511a8b', '#1a8b6e', '#8b1a22', '#1a4e8b', '#5a8b1a',
    '#6e1a8b', '#7b8b1a', '#1a8b3d', '#8b2d1a', '#1a228b', '#6b8b1a', '#8b1a7b', '#1a7b8b', '#838b1a', '#431a8b',
    '#228b1a', '#8b1a4e', '#64676E'
]  # 63 colors for ascii_uppercase + ascii_lowercase + digits + '_'


class SpaceState1DFormatter:
    def __init__(self) -> None:
        # We have these here for maximal configuration.
        self.default_colors = COLOR_PALETTE.copy()
        self.chars = ascii_uppercase + ascii_lowercase + digits + '_'
        self.highlight_cells_with_id: set[int] | frozenset[int] = set()
        self.highlighted_cell_style: str = 'on yellow'

        # this holds pre-initiated Text objects for every character
        self._rich_mapping: dict[int, Text] = {}

        # initial build
        self.config()

    def config(self, styling: bool = True,
               style_on_symbol: bool = False,
               show_symbols: bool = True,
               cell_padding: bool = True,
               style_mapping_override: dict[str, str] | None = None,
               clear_default_styles_on_override: bool = False,
               symbol_mapping_override: dict[str, str] | None = None) -> None:
        """
        Pre-computes the Text objects for the mapping.
        All logic is handled here so __call__ is a pure lookup.
        """
        if style_mapping_override is None: style_mapping_override = {}
        if symbol_mapping_override is None: symbol_mapping_override = {}

        new_mapping = {}
        for char in self.chars:
            # determine Display Symbol
            display = symbol_mapping_override.get(char, char) if show_symbols else ""
            # apply Padding
            content = f" {display} " if cell_padding else display
            # determine Style
            style = ""
            ordinal: int = ord(char)  # so that cells are correctly mapped.
            color_idx: int = abs(ordinal - 65) % len(self.default_colors)
            if styling:
                default_style = self.default_colors[color_idx] if style_on_symbol \
                    else f'on {self.default_colors[color_idx]}'
                if clear_default_styles_on_override and style_mapping_override:
                    default_style = ''
                style = style_mapping_override.get(char, default_style)
            # create and cache the Text object
            new_mapping[ordinal] = Text(content, style=style, end='')
        self._rich_mapping = new_mapping

    def __call__(self, s: SpaceState1D) -> Text:
        """Fast join using the pre-computed mapping. Also highlight specific vec matching highlight_cells_with_id."""
        rm = self._rich_mapping
        highlight_cells_with_id = self.highlight_cells_with_id
        highlighted_cell_style = self.highlighted_cell_style
        def iter_cells() -> Iterator[Text]:
            if highlight_cells_with_id:
                for c in s.vec.all_cells:
                    cell: Text = rm.get(c.quanta, Text(chr(c.quanta), end=''))
                    if c.id in highlight_cells_with_id:
                        cell = cell.copy()
                        cell.stylize(highlighted_cell_style)
                    yield cell
            else:
                for c in s.vec:
                    yield rm.get(c, Text(chr(c), end=''))
        return Text(end='').join(iter_cells())

    def convert_pure_str(self, string: str) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        rm = self._rich_mapping
        return Text(end='').join(rm.get(ord(c), Text(c, end='')) for c in string)

    def convert_pure_sequence(self, seq: Sequence[int]) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        rm = self._rich_mapping
        return Text(end='').join(rm.get(i, Text(chr(i), end='')) for i in seq)


if __name__ == "__main__":
    from implementations.sss import SSS
    from rich.console import Console
    system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space='AB')
    system.evolve(20)
    formatter = SpaceState1DFormatter()
    formatter.highlight_cells_with_id = {6, 26}
    formatter.config(show_symbols=True)
    console = Console(width=1000)
    for event in system.events:
        console.print(formatter(next(event.spaces)))
