from textual.widgets import Collapsible, TabPane
from textual.app import App
from typing import Optional
from studio.model import Plugin, Model

class P(Plugin):
    def __init__(self) -> None:
        self.name: str = "analysis"
        self.model: Optional[Model] = None
        self.app: Optional[App] = None

    def panel(self) -> TabPane | None:
        return TabPane(self.name.title())

    def controls(self) -> list[Collapsible]:
        return []
plugin = P()
