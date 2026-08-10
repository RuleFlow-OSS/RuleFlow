"""
prettier.py
Rich-based visualization wrapper for the Flow engine's SpaceState.

TODO:
- Add options for Nd rendering.
"""
from typing import Iterator, Iterable
from rich.text import Text
from rich.console import Console
from core.topologies.nd_space import SpaceState1D
from core.topologies.tooling.rff_encoding import chr_rff
from typing import Literal


# Color Palette (64 Colors)
COLOR_PALETTE: list[str] = ['#5a8b1a', '#00728b', '#8b221a', '#1a648b', '#6b8b1a', '#1a2d8b', '#1a4e8b', '#8b2d1a',
                            '#8b1a7b', '#5a8b1b', '#8b691a', '#8b1a33', '#8b1a44', '#7b8b1a', '#1a8b22', '#8b7b1a',
                            '#64676E', '#8b1a6e', '#8b0000', '#7e8b1a', '#8b1a4e', '#2d8b2d', '#8b1a82', '#431a8b',
                            '#1a7e8b', '#628b1a', '#8b431a', '#6e1a8b', '#348b1a', '#4e1a8b', '#8b1a62', '#8b5e1a',
                            '#1a8b43', '#3c1a8b', '#1a5c8b', '#1a4e8b', '#5c1a8b', '#228b1a', '#8b3d1a', '#6e1a8b',
                            '#1a7b8b', '#1a8b34', '#8b1a22', '#8b511a', '#8b1a43', '#1a8b51', '#3d8b1a', '#1a8b4e',
                            '#838b1a', '#1a8b6e', '#6b8b1a', '#1a8b7e', '#1a788b', '#1a3d8b', '#4e8b1a', '#471a8b',
                            '#7b8b1a', '#1a8b3d', '#221a8b', '#511a8b', '#1a228b', '#758b1a', '#8b1a72', '#2d1a8b']


class SpaceState1DFormatter:
    """
    IMPORTANT NOTES:
    - `reset_cache()` must be called when changing any attribute other than `encode_using_property`, `style_using_property`, `highlight_cells_with_id` or `highlight_cells_in_generation`.
    """

    def __init__(self) -> None:
        # this holds pre-initiated Text objects for every character
        self.rich_cache: dict[int | tuple[int, int] | tuple[int, str], Text] = {}

        # special modifiers
        self.highlight_cells_with_id: dict[int, str] = {}
        self.highlight_cells_in_generation: dict[int, str] = {}

        # style properties
        self.styling: bool = True
        self.style_on_background: bool = True
        self.clear_default_styles_on_override: bool = False
        self.style_using_property: Literal["quanta", "generation", "id"] = "quanta"
        self.style_mapping_override: dict[int, str] = {}

        # render properties
        self.show_symbols: bool = True
        self.encode_ordinals: bool = True
        self.cell_width: int = 3
        self.encode_using_property: Literal["quanta", "generation", "id"] = "quanta"
        self.symbol_mapping_override: dict[int, str] = {}

    def _ordinal_style(self, o: int) -> str:
        if not self.styling:
            return ""
        color_idx: int = o % len(COLOR_PALETTE)
        if self.style_mapping_override:
            if self.clear_default_styles_on_override:
                default_style = ""
            else:
                default_style = f"on {COLOR_PALETTE[color_idx]}" if self.style_on_background \
                    else COLOR_PALETTE[color_idx]
            return self.style_mapping_override.get(o, default_style)
        else:
            return f"on {COLOR_PALETTE[color_idx]}" if self.style_on_background \
                else COLOR_PALETTE[color_idx]

    def _ordinal_encode(self, o: int) -> str:
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
        pm: dict[str, int] = {'quanta': 0, 'generation': 1, 'id': 2}
        encode_using_property: int = pm[self.encode_using_property]
        style_using_property: int = pm[self.style_using_property]
        if self.highlight_cells_with_id or self.highlight_cells_in_generation:
            def iter_cells() -> Iterator[Text]:
                for p in zip(s.vec.data, s.vec.generations, s.vec.ids):
                    highlight_style: str = (self.highlight_cells_with_id.get(p[2], '') or
                                            self.highlight_cells_in_generation.get(p[1], ''))
                    or_: int = p[encode_using_property]
                    os_: int = p[style_using_property]
                    if highlight_style:
                        yield rm.setdefault((or_, highlight_style), Text(self._ordinal_render(or_),
                                                                         style=highlight_style, end=''))
                    else:
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
    from implementations.sss import SSS
    from rich.console import Console
    system = SSS(rule_set=["ABA -> AAB", "A -> ABA"], initial_space="AB")
    system.build_multiway_space_links = True
    system.evolve(30)

    console = Console(width=1000)
    formatter = SpaceState1DFormatter()
    formatter.encode_using_property = 'id'
    formatter.style_using_property = 'id'
    formatter.encode_ordinals = True
    formatter.cell_width = 3
    formatter.styling = True
    # formatter.highlight_cells_with_id = {188: 'on black'}

    # Test Branch Walks
    for idx, ds in enumerate(reversed(list(system.walk_branch((-1, 0))))):
        console.print(idx, '\t', formatter(ds))

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
