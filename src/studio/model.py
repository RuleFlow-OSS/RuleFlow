"""The model side of the MVC paradigm

# TODO:
- Clean up the way the Model part of the MVC is designed.
- Connect it up to the View/Controller.
"""
from typing import Optional, Any
from lang import FlowLangBase as FlowL, FlowLang  # in the implementation
from abc import ABC, abstractmethod
from textual.widgets import TabPane, Collapsible
from textual.app import App as TextualApp
from core.signals import Signal
from pathlib import Path


class Flow:
    """
    Represents
    """
    def __init__(self):
        self.name: str = ""
        self.file_path: Path = Path()
        self.src: str = ""
        self.flow: FlowL | None = None
        self.is_dirty: bool = False

    def save_file(self):
        pass

    def open_file(self):
        pass


class Model:
    """
    The source of truth for the application state (a Singleton Pattern).
    Manages the current workspace and open file flows.
    """
    on_load: Signal = Signal()
    on_save: Signal = Signal()

    def __init__(self) -> None:
        self.root_path: Optional[Path] = None

        # Flow Classes (selected when creating a new Flow instance)
        self.flow_classes: dict[str, type[FlowL]] = {
            "FlowLang": FlowLang
        }

        # Active Flows
        self.flows: list[Flow] = []
        self.active_flow: Optional[Flow] = None

    def set_root_path(self, path: str | Path) -> None:
        """Sets the working directory."""
        self.root_path = Path(path)

    def get_flow_options(self) -> list[str]:
        """
        Returns list of tuples formatted for a Textual Select widget.
        Format: [(Label, Value), ...]
        """
        return [f.name for f in self.flows]

    # ==== Flow Class ====
    @property
    def current_flow_class(self) -> type[FlowL]:
        return self.flow_classes[self.selected_flow_class]

    def set_selected_flow_class(self, name: str) -> None:
        self.selected_flow_class = name

    def register_flow_class(self, flow_class: type[FlowL]) -> None:
        self.flow_classes[flow_class.__name__] = flow_class

    # ==== Persistence ====
    def save(self, to_file: str) -> None:
        pass  # TODO implement

    @classmethod
    def load(cls, from_file: str) -> Model:
        pass  # TODO implement


# ================ Client Implemented  ================
class Plugin(ABC):
    """
    Any class that inherits from this, becomes a plugin and is expected to implement the methods below.
    Only one instance of this class is expected for each plugin PER APP.
    If session/flow-instance-specific behavior is desired, the session change signal must be watched and handled.
    """

    @abstractmethod
    def __init__(self, model: Model, app: TextualApp) -> None:
        pass

    @abstractmethod
    def panel(self) -> TabPane | None:
        """Returns the widget to be displayed in the panel for this plugin."""
        return None

    @abstractmethod
    def controls(self) -> tuple[str, list[Collapsible]] | None:
        """Returns the controls (in renderable format) for modifying this plugin's behavior."""
        return None
