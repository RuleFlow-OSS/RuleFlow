"""
prettier.py
Rich-based visualization wrapper for the Flow engine's SpaceState.

TODO:
- Add options for Nd rendering.
"""
from typing import Iterator, Iterable
from rich.text import Text
from core.topologies.nd_space import SpaceState1D
from core.topologies.tooling.rff_encoding import chr_rff
from random import Random


# Ordered Color Palette (64 Colors)
COLOR_PALETTE: list[str] = [
    '#ff0000', '#ff1400', '#ff2800', '#ff3d00', '#ff5100', '#ff6500', '#ff7900', '#ff8e00',
    '#ffa200', '#ffb600', '#ffca00', '#ffdf00', '#fff300', '#f7ff00', '#e3ff00', '#ceff00',
    '#baff00', '#a6ff00', '#92ff00', '#7dff00', '#69ff00', '#55ff00', '#41ff00', '#2dff00',
    '#18ff00', '#04ff00', '#00ff10', '#00ff24', '#00ff39', '#00ff4d', '#00ff61', '#00ff75',
    '#00ff8a', '#00ff9e', '#00ffb2', '#00ffc6', '#00ffdb', '#00ffef', '#00fbff', '#00e7ff',
    '#00d2ff', '#00beff', '#00aaff', '#0096ff', '#0081ff', '#006dff', '#0059ff', '#0045ff',
    '#0030ff', '#001cff', '#0008ff', '#0c00ff', '#2000ff', '#3500ff', '#4900ff', '#5d00ff',
    '#7100ff', '#8600ff', '#9a00ff', '#ae00ff', '#c200ff', '#d700ff', '#eb00ff', '#ff00ff'
]


class SpaceState1DFormatter:
    """
    IMPORTANT NOTES:
    - `reset_cache()` must be called when changing any attribute other than `encode_using_property`, `style_using_property`, `highlight_cells_with_id` or `highlight_cells_in_generation`.
    """

    def __init__(self) -> None:
        # this holds pre-initiated Text objects for every character
        self.rich_cache: dict[int | tuple[int, int] | tuple[int, str], Text] = {}

        # special properties
        self._random_engine: Random = Random()
        self.COLOR_PALETTE: list[str] = []
        self.color_palette_seed: int = 19
        self.set_color_palette_seed(self.color_palette_seed)

        # special modifiers
        self.highlight_cells_with_id: dict[int, str] = {}
        self.highlight_cells_in_generation: dict[int, str] = {}

        # style properties
        self.styling: bool = True
        self.default_char_color: str = 'black'
        self.style_on_background: bool = True
        self.clear_default_styles_on_override: bool = False
        self.style_using_property: int = 0
        self.style_mapping_override: dict[int, str] = {}

        # render properties
        self.show_symbols: bool = True
        self.encode_ordinals: bool = True
        self.cell_width: int = 3
        self.encode_using_property: int = 0
        self.symbol_mapping_override: dict[int, str] = {}

    def _ordinal_style(self, o: int) -> str:
        if not self.styling or o == -1:  # don't encode wildcards
            return ""
        color_idx: int = o % len(self.COLOR_PALETTE)
        if self.style_mapping_override:
            if self.clear_default_styles_on_override:
                default_style = ""
            else:
                default_style = f"{self.default_char_color} on {self.COLOR_PALETTE[color_idx]}" \
                    if self.style_on_background else self.COLOR_PALETTE[color_idx]
            return self.style_mapping_override.get(o, default_style)
        else:
            return f"{self.default_char_color} on {self.COLOR_PALETTE[color_idx]}" if self.style_on_background \
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

    def __call__(self, s: SpaceState1D) -> Text:  # TODO: maybe cache this whole function
        """Fast join using the pre-computed mapping. Also highlight specific vec matching highlight_cells_with_id."""
        rm = self.rich_cache
        encode_using_property: int = self.encode_using_property
        style_using_property: int = self.style_using_property
        if self.highlight_cells_with_id or self.highlight_cells_in_generation:
            def iter_cells() -> Iterator[Text]:
                for p in zip(s.vec.data, s.vec.generations, s.vec.ids):
                    highlight_style: str = (self.highlight_cells_with_id.get(p[2], '') or
                                            self.highlight_cells_in_generation.get(p[1], ''))
                    or_: int = p[encode_using_property]
                    if highlight_style:
                        yield rm.setdefault((or_, highlight_style), Text(self._ordinal_render(or_),
                                                                         style=highlight_style, end=''))
                    else:
                        os_: int = p[style_using_property]
                        yield rm.setdefault((or_, os_), Text(self._ordinal_render(or_),
                                                             style=self._ordinal_style(os_), end=''))
        else:
            def iter_cells() -> Iterator[Text]:
                for p in zip(s.vec.data, s.vec.generations, s.vec.ids):
                    or_: int = p[encode_using_property]
                    os_: int = p[style_using_property]
                    yield rm.setdefault((or_, os_), Text(self._ordinal_render(or_),
                                                         style=self._ordinal_style(os_), end=''))
        return Text(end='').join(iter_cells())

    def set_color_palette_seed(self, n: int | None):
        if n is None:
            self.COLOR_PALETTE = COLOR_PALETTE.copy()
        else:
            self._random_engine.seed(n)
            self.COLOR_PALETTE = COLOR_PALETTE.copy()
            self._random_engine.shuffle(self.COLOR_PALETTE)

    def reset_cache(self):
        self.rich_cache.clear()

    def convert_pure_sequence(self, seq: Iterable[int]) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        rm = self.rich_cache
        return Text(end='').join(rm.get(c, Text(self._ordinal_render(c), style=self._ordinal_style(c), end='')) for c in seq)

    def convert_pure_str(self, string: str) -> Text:
        """Utility method in case a given string needs to be styled the same as the space states (can be used in a ruleset printer for instance)."""
        return self.convert_pure_sequence((ord(c) for c in string))


if __name__ == "__main__":
    # Test the color palette
    from rich.console import Console
    console = Console(width=1000)
    console.print(Text('').join([Text('  ', style=f'on {c}') for c in COLOR_PALETTE]))

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
    #         formatter.style_using_property = 'generation'
    #         # formatter.reset_cache()

    # Test Cell Lifespan Detection
    # formatter.encode_using_property = 'id'
    # formatter.style_using_property = 'id'
    # formatter.encode_ordinals = False
    # formatter.reset_cache()
    # for idx, event in enumerate(system.events):
    #     console.print(idx, '\t', formatter(next(event.spaces)))
    # print(system.find_cell_lifespan([60, 82, 218], slice(0, -1)))
