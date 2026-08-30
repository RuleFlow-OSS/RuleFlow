"""
prettier.py
Rich-based visualization wrapper for the Flow engine's SpaceState.

TODO:
- Add options for Nd rendering.
"""
from typing import Iterator, Iterable, Literal, Sequence
from rich.text import Text, Span, Style
from core.topologies.nd_space import SpaceState1D
from core.topologies.tooling.rff_encoding import chr_rff
from random import Random


# Ordered Color Palette (64 Colors)
COLOR_PALETTE: list[str] = [
    # Red to Yellow (8 steps to reduce red dominance)
    '#ff0000', '#ff2000', '#ff4000', '#ff6000', '#ff8000', '#ffa000', '#ffc000', '#ffe000',

    # Yellow to Green (12 steps)
    '#ffff00', '#eaff00', '#d5ff00', '#c0ff00', '#abff00', '#96ff00', '#81ff00', '#6cff00',
    '#57ff00', '#42ff00', '#2dff00', '#18ff00',

    # Green to Cyan (12 steps)
    '#00ff00', '#00ff15', '#00ff2a', '#00ff3f', '#00ff54', '#00ff69', '#00ff7e', '#00ff93',
    '#00ffa8', '#00ffbd', '#00ffd2', '#00ffe7',

    # Cyan to Blue (12 steps)
    '#00ffff', '#00eaff', '#00d5ff', '#00c0ff', '#00abff', '#0096ff', '#0081ff', '#006cff',
    '#0057ff', '#0042ff', '#002dff', '#0018ff',

    # Blue to Magenta (11 steps)
    '#0000ff', '#1700ff', '#2e00ff', '#4500ff', '#5c00ff', '#7300ff', '#8a00ff', '#a100ff',
    '#b800ff', '#cf00ff', '#e600ff',

    # Magenta back to Red (Compressed to 9 steps, stopping right before pure red for a perfect loop)
    '#ff00ff', '#ff00e3', '#ff00c7', '#ff00ab', '#ff008f', '#ff0073', '#ff0057', '#ff003b',
    '#ff001f'
]


class SpaceState1DFormatter:
    def __init__(self) -> None:
        # special properties
        self._random_engine: Random = Random()
        self.COLOR_PALETTE: list[str] = []
        self.color_palette_seed: int = 170
        self.set_color_palette_seed(self.color_palette_seed)

        # special modifiers
        self.highlight_cells_with_id: dict[int, str] = {}
        self.highlight_cells_in_generation: dict[int, str] = {}

        # cell style properties
        self.styling: bool = True
        self.style_on_background: bool = True
        self.clear_default_styles_on_override: bool = False
        self.style_using_property: int = 0
        self.style_mapping_override: dict[int, str] = {}

        # cell render properties
        self.show_symbols: bool = True
        self.encode_ordinals: bool = True
        self.cell_width: int = 3
        self.encode_using_property: int = 0
        self.symbol_mapping_override: dict[int, str] = {}

        # base properties
        self.base_style: str = ''
        self.justify: Literal["default", "left", "center", "right", "full"] = 'default'

    def _ordinal_style(self, o: int) -> str:
        # remember that textual will cache the style strings
        if not self.styling or o == -1:  # don't encode wildcards
            return ""
        color_idx: int = o % len(self.COLOR_PALETTE)
        if self.style_mapping_override:
            if self.clear_default_styles_on_override:
                default_style = ""
            else:
                default_style = f"on {self.COLOR_PALETTE[color_idx]}" \
                    if self.style_on_background else self.COLOR_PALETTE[color_idx]
            return self.style_mapping_override.get(o, default_style)
        else:
            return f"on {self.COLOR_PALETTE[color_idx]}" if self.style_on_background \
                else self.COLOR_PALETTE[color_idx]

    def _ordinal_encode(self, o: int) -> str:
        if o == -1:
            return '.'
        if self.encode_ordinals:
            try: return chr_rff(o)
            except: return "퟼"
        return str(o)

    def _ordinal_render(self, o: int) -> str:
        width = self.cell_width
        if self.symbol_mapping_override:
            display: str = self.symbol_mapping_override.get(o, self._ordinal_encode(o)) if self.show_symbols else ""
            return f"{display:^{width}}" if width else display
        else:
            display: str = self._ordinal_encode(o) if self.show_symbols else ""
            return f"{display:^{width}}" if width else display

    def __call__(self, s: SpaceState1D) -> Text:
        """Fast join using the pre-computed mapping. Also highlight specific vec matching highlight_cells_with_id."""
        # Hoist methods out of the loop to avoid repeating dictionary lookups on `self`
        ordinal_render = self._ordinal_render
        ordinal_style = self._ordinal_style
        chars: list[str] = []
        spans: list[Span] = []
        pos: int = 0
        if self.highlight_cells_with_id or self.highlight_cells_in_generation:
            highlight_cells_with_id = self.highlight_cells_with_id
            highlight_cells_in_generation = self.highlight_cells_in_generation
            encode_using_property = self.encode_using_property
            style_using_property = self.style_using_property
            for p in zip(s.vec.data, s.vec.gens, s.vec.ids):
                highlight_style: str = (highlight_cells_with_id.get(p[2], '') or
                                        highlight_cells_in_generation.get(p[1], ''))
                char: str = ordinal_render(p[encode_using_property])
                char_len: int = len(char)
                if highlight_style:
                    spans.append(Span(pos, pos + char_len, highlight_style))
                else:
                    spans.append(Span(pos, pos + char_len, ordinal_style(p[style_using_property])))
                pos += char_len
                chars.append(char)
        else:
            sources: tuple[Sequence[int], Sequence[int], Sequence[int]] = (s.vec.data, s.vec.gens, s.vec.ids)
            ordinal_src: Sequence[int] = sources[self.encode_using_property]
            style_src: Sequence[int] = sources[self.style_using_property]
            for os, ss in zip(ordinal_src, style_src):
                char: str = ordinal_render(os)
                char_len: int = len(char)
                spans.append(Span(pos, pos + char_len, ordinal_style(ss)))
                pos += char_len
                chars.append(char)
        return Text(''.join(chars), style=self.base_style, justify=self.justify, spans=spans, end='')  # type: ignore

    def set_color_palette_seed(self, n: int | None):
        if n is None:
            self.COLOR_PALETTE = COLOR_PALETTE.copy()
        else:
            self._random_engine.seed(n)
            self.COLOR_PALETTE = COLOR_PALETTE.copy()
            self._random_engine.shuffle(self.COLOR_PALETTE)

    def convert_pure_sequence(self, seq: Iterable[int]) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        # Hoist methods out of the loop to avoid repeating dictionary lookups on `self`
        ordinal_render = self._ordinal_render
        ordinal_style = self._ordinal_style
        chars: list[str] = []
        spans: list[Span] = []
        pos: int = 0
        for c in seq:
            char: str = ordinal_render(c)
            char_len: int = len(char)
            spans.append(Span(pos, pos + char_len, ordinal_style(c)))  # append a span strictly for this specific character
            chars.append(char)
            pos += char_len
        return Text(''.join(chars), style=self.base_style, justify=self.justify, spans=spans, end='')  # type: ignore

    def convert_pure_str(self, string: str) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        return self.convert_pure_sequence(string.encode())


if __name__ == "__main__":
    # Test the color palette
    from rich.console import Console
    console = Console(width=1000)
    console.print(Text('').join([Text('  ', style=f'on {c}') for c in COLOR_PALETTE]))
    console.print(Text("TESTING", style=f'black', spans=[Span(0, 3, Style(bgcolor='green'))]))

    # from implementations.sss import SSS
    # from rich.console import Console
    # system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space="AB")
    # system.build_multiway_space_links = True
    # system.evolve(30)
    #
    # console = Console(width=1000)
    # formatter = SpaceState1DFormatter()
    # formatter.encode_using_property = 0
    # formatter.style_using_property = 0
    # formatter.encode_ordinals = True
    # formatter.cell_width = 3
    # formatter.styling = True
    # # formatter.highlight_cells_with_id = {188: 'on black'}
    #
    # # Test Branch Walks
    # for idx, ds in enumerate(reversed(list(system.walk_branch((-1, 0))))):
    #     console.print(idx, '\t', formatter(ds))

    # Test mid-change
    # for idx, event in enumerate(system.events):
    #     console.print(idx, '\t', formatter(next(event.spaces)))
    #     if idx == 43:
    #         formatter.encode_using_property = 'quanta'
    #         formatter.style_using_property = 'gen'
    #         # formatter.reset_cache()

    # Test Cell Lifespan Detection
    # formatter.encode_using_property = 'id'
    # formatter.style_using_property = 'id'
    # formatter.encode_ordinals = False
    # formatter.reset_cache()
    # for idx, event in enumerate(system.events):
    #     console.print(idx, '\t', formatter(next(event.spaces)))
    # print(system.find_cell_lifespan([60, 82, 218], slice(0, -1)))
