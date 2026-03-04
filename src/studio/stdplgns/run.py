# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox
from textual.widget import Widget
from textual.containers import ScrollableContainer
from textual.app import App

# Standard Imports
from typing import Optional, Iterator
from studio.model import Plugin, Model
from studio.stdplgns.lib.widgets import Button

class P(Plugin):
    def __init__(self) -> None:
        self.name: str = 'run'
        self.model: Optional[Model] = None
        self.app: Optional[App] = None

    def panel(self) -> TabPane | None:
        # TODO: connect up the controls and the Flow backend......
        return TabPane(
            self.name.title(),
            ScrollableContainer(
                Collapsible(Collapsible(expanded_symbol='-', collapsed_symbol='+')),
                Collapsible(), Collapsible())
        )

    def controls(self) -> Iterator[Widget]:
        # NOTE: there aren't that many settings for the run tab due to most controls being available through the DSL.
        with Collapsible(title='Hot Reload', collapsed=False):
            self.hot_mode = Checkbox('Enable Hot Reload Mode')
            yield self.hot_mode
            self.hot_n_changes = Input(type='integer', value='1')
            self.hot_n_changes.border_title = 'Re-run after N changes'
            yield self.hot_n_changes
            self.hot_timeout = Input(type='number', value='500')
            self.hot_timeout.border_title = 'Timeout (ms)'
            yield self.hot_timeout

        with Collapsible(title='Profiler', collapsed=False):
            self.enable_progress_bar = Checkbox('Progress bar')
            yield self.enable_progress_bar
            self.enable_program_stats = Checkbox('Resource usage stats')
            yield self.enable_program_stats

plugin = P()
