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
from typing import Literal
from sys import maxunicode
from wcwidth import wcwidth


# Character Set
PRINTABLE_CHARS: list[str] = [
    c for c in map(chr, range(33, maxunicode + 1))
    if c.isprintable() and not c.isspace() and wcwidth(c) == 1
]
PRINTABLE_CHARS = (
        PRINTABLE_CHARS[32:58] +  # A-Z
        PRINTABLE_CHARS[64:90] +  # a-z
        PRINTABLE_CHARS[15:25] +  # 0-9

        # stitch together the leftover gaps
        PRINTABLE_CHARS[:15] +  # Punctuation before numbers (! to /)
        PRINTABLE_CHARS[25:32] +  # Punctuation between numbers and uppercase (: to @)
        PRINTABLE_CHARS[58:64] +  # Punctuation between uppercase and lowercase ([ to `)
        PRINTABLE_CHARS[90:]  # Everything after lowercase ({ and beyond)
)
CHAR_TO_INDEX: dict[str, int] = {char: idx for idx, char in enumerate(PRINTABLE_CHARS)}
# noinspection PyShadowingBuiltins
def chr(o: int) -> str:
    return PRINTABLE_CHARS[o]
# noinspection PyShadowingBuiltins
def ord(c: str) -> int:
    return CHAR_TO_INDEX[c]


# Color Palette (64 Colors)
COLOR_PALETTE: list[str] = [
    '#1a4e8b', '#8b0000', '#2d8b2d', '#8b1a72', '#00728b', '#8b5e1a', '#4e1a8b', '#6b8b1a', '#8b1a43', '#1a7e8b',
    '#7b8b1a', '#5c1a8b', '#1a8b43', '#8b431a', '#1a2d8b', '#8b7b1a', '#8b1a62', '#1a8b7e', '#3c1a8b', '#3d8b1a',
    '#8b221a', '#1a5c8b', '#1a8b22', '#6e1a8b', '#5a8b1a', '#8b1a82', '#1a8b51', '#8b691a', '#2d1a8b', '#4e8b1a',
    '#8b1a33', '#1a788b', '#7e8b1a', '#471a8b', '#1a8b34', '#8b3d1a', '#1a3d8b', '#628b1a', '#8b1a6e', '#1a648b',
    '#758b1a', '#221a8b', '#1a8b4e', '#8b511a', '#348b1a', '#511a8b', '#1a8b6e', '#8b1a22', '#1a4e8b', '#5a8b1a',
    '#6e1a8b', '#7b8b1a', '#1a8b3d', '#8b2d1a', '#1a228b', '#6b8b1a', '#8b1a7b', '#1a7b8b', '#838b1a', '#431a8b',
    '#228b1a', '#8b1a4e', '#64676E', '#8b1a44'
]


class SpaceState1DFormatter:
    def __init__(self) -> None:
        # this holds pre-initiated Text objects for every character
        self._rich_cache: dict[int, Text] = {}

        # special modifiers
        self.highlight_cells_with_id: set[int] | frozenset[int] = set()
        self.highlighted_cell_style: str = 'on yellow'

        # style properties
        self.style_on_background: bool = True
        self.style_mapping_override: dict[int, str] = {}
        self.clear_default_styles_on_override: bool = False

        # render properties
        self.styling: bool = True
        self.cell_property: Literal["quanta", "generation", "id"] | None = None
        self.encode_ordinals: bool = True
        self.show_symbols: bool = True
        self.cell_padding: bool = True
        self.symbol_mapping_override: dict[int, str] = {}

        # initial build
        self.sync_cache()

    def _ordinal_style(self, o: int) -> str:
        color_idx: int = abs(int(o) - 65) % len(COLOR_PALETTE)
        if self.style_mapping_override:
            if self.clear_default_styles_on_override:
                default_style = ''
            else:
                default_style = f'on {COLOR_PALETTE[color_idx]}' if self.style_on_background \
                    else COLOR_PALETTE[color_idx]
            return self.style_mapping_override.get(o, default_style)
        else:
            return f'on {COLOR_PALETTE[color_idx]}' if self.style_on_background \
                else COLOR_PALETTE[color_idx]

    def _ordinal_encode(self, o: int) -> str:
        if self.encode_ordinals:
            try: return chr(o)
            except IndexError: return "퟼"
        return str(o)

    def _ordinal_render(self, o: int) -> str:
        if self.symbol_mapping_override:
            display: str = self.symbol_mapping_override.get(o, self._ordinal_encode(o)) if self.show_symbols else ""
            return f" {display} " if self.cell_padding else display
        else:
            display: str = self._ordinal_encode(o) if self.show_symbols else ""
            return f" {display} " if self.cell_padding else display

    def sync_cache(self, **kwargs) -> None:
        """
        Pre-computes (or syncs to the parameters) the Text objects for the mapping.
        All logic is handled here so __call__ is a pure lookup.
        """
        self.__dict__.update(kwargs)
        styling: bool = self.styling
        new_mapping = {}
        for ordinal in range(94):
            content: str = self._ordinal_render(ordinal)
            style: str = ''
            if styling:
                style = self._ordinal_style(ordinal)
            new_mapping[ordinal] = Text(content, style=style, end='')  # cache the Text object
        self._rich_cache = new_mapping

    def __call__(self, s: SpaceState1D) -> Text:
        """Fast join using the pre-computed mapping. Also highlight specific vec matching highlight_cells_with_id."""
        rm = self._rich_cache
        def iter_cells() -> Iterator[Text]:
            if self.highlight_cells_with_id or self.cell_property:
                cell_property: str = 'quanta' if self.cell_property is None else self.cell_property
                for c in s.vec.all_cells:
                    o: int = getattr(c, cell_property)
                    cell: Text = rm.get(o, Text(self._ordinal_render(o), style=self._ordinal_style(o), end=''))
                    if c.id in self.highlight_cells_with_id:
                        cell = cell.copy()
                        cell.stylize(self.highlighted_cell_style)
                    yield cell
            else:
                for c in s.vec:
                    yield rm.get(c, Text(self._ordinal_render(c), style=self._ordinal_style(c), end=''))
        return Text(end='').join(iter_cells())

    def convert_pure_str(self, string: str) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        rm = self._rich_cache
        return Text(end='').join(rm.get(ord(c), Text(c, end='')) for c in string)

    def convert_pure_sequence(self, seq: Sequence[int]) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        rm = self._rich_cache
        return Text(end='').join(rm.get(i, Text(chr(i), end='')) for i in seq)


if __name__ == "__main__":
    from implementations.sss import SSS
    from rich.console import Console
    system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space='AB')
    system.evolve(20)
    formatter = SpaceState1DFormatter()
    # formatter.highlight_cells_with_id = {6, 26}
    # formatter.sync_cache()
    console = Console(width=1000)
    for event in system.events:
        console.print(formatter(next(event.spaces)))
