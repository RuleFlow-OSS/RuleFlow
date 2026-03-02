from textual.widgets import Collapsible, TabPane
from textual.widget import Widget
from textual.containers import ScrollableContainer
from textual.app import App
from typing import Optional
from studio.model import Plugin, Model

class P(Plugin):
    def __init__(self) -> None:
        self.name: str = "run"
        self.model: Optional[Model] = None
        self.app: Optional[App] = None

    def panel(self) -> TabPane | None:
        return TabPane(
            self.name.title(),
            ScrollableContainer(
                Collapsible(Collapsible(expanded_symbol="-", collapsed_symbol="+")),
                Collapsible(), Collapsible())
        )

    def controls(self) -> list[Widget]:
        return [Collapsible(title=self.name.title())]
plugin = P()
