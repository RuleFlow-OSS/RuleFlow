"""
Placeholder for future analysis tooling.
"""
from textual.widgets import TabPane, Label
from textual.containers import VerticalScroll
from typing import Iterator
from textual.widget import Widget

from studio.model import Plugin

class P(Plugin):
    name = 'analysis'
    file_types = ['.sss']

    def on_initialized(self) -> None:
        pass

    def controls(self) -> Iterator[Widget]:
        yield Label("To be implemented")

    def panel(self) -> TabPane | None:
        return TabPane(
            self.name.title(),
            VerticalScroll(Label("To be implemented"), classes="p-4")
        )
