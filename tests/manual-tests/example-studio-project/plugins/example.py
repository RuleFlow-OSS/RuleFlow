# Textual Imports
from textual.widgets import TabPane, Label, Collapsible
from textual.widget import Widget

# Standard Imports
from typing import Iterator
from studio.model import Plugin


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'Example'

    def controls(self) -> Iterator[Widget]:
        return iter([Collapsible(Label("Settings go here!"), Label(" ... "), title='Example Setting')])

    def panel(self) -> TabPane | None:
        return TabPane(self.name.title(), Label(' This is the panel that would be developed in this plugin.'))


plugin = P()
