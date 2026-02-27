"""The model side of the MVC paradigm

# TODO:
- Clean up the way the Model part of the MVC is designed.
- Connect it up to the View/Controller.
"""
from typing import Optional, Any
from lang import FlowLangBase, FlowLang  # in the implementation
from abc import ABC, abstractmethod
from textual.widgets import TabPane, Collapsible
from textual.app import App as TextualApp
from core.signals import Signal
from copy import deepcopy

# used for dynamic imports and path management
from pathlib import Path
import importlib.util
import inspect
import sys
import importlib


class Flow:
    """
    Represents
    """
    def __init__(self):
        self.flow: FlowLangBase = FlowLang()
        self.src: str = ""

        # metadata
        self.name: str = ""
        self.file_path: Path = Path()
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

    def __init__(self, name: str, project_path: Path) -> None:
        # ======== Basic Project Config ========
        self.project_name: str = name  # name the user has given the project
        self.project_path: Path = project_path

        # ======== Plugins ========
        self.plugins: list[Plugin] = []

        # add builtin plugins
        from studio.stdplgns import analysis, output, run
        for module in (analysis, output, run):
            for _, obj in inspect.getmembers(module):
                if isinstance(obj, Plugin):
                    self.plugins.append(obj)
        # load all plugins
        for pp in (self.project_path / "plugins").glob("*.py"):
            module_name = f"plugins.{pp.stem}"  # make it appear as if it lives in a package called plugins.
            # Dynamically import module
            spec = importlib.util.spec_from_file_location(module_name, pp)  # tells Python how to load the file
            module = importlib.util.module_from_spec(spec)  # allocates module object
            sys.modules[module_name] = module  # makes it importable and unique
            spec.loader.exec_module(module)  # populates module with code and objects
            # Look for instances of Plugin inside the module
            for _, obj in inspect.getmembers(module):
                if isinstance(obj, Plugin):
                    self.plugins.append(obj)

        # ======== Active Flows ========
        self.flows: list[Flow] = []
        self.active_flow: Optional[Flow] = None

        # add default flow
        self.flows.append(_:=Flow())
        _.name = "Root"
        self.active_flow = _

    def get_flow_options(self) -> list[str]:
        """
        Returns list of tuples formatted for a Textual Select widget.
        """
        return [f.name for f in self.flows]

    def create_new_flow(self, name: str, branch_from_current: bool) -> bool:
        """Create a new Flow object and return True if the flow was created, otherwise False."""
        if name in (f.name for f in self.flows):
            return False
        self.flows.append(_:=(
            deepcopy(self.active_flow) if self.active_flow and branch_from_current else Flow()
        ))
        _.name = name
        self.active_flow = _
        return True

    def delete_selected_flow(self) -> None:
        new_flow_idx: int = self.flows.index(self.active_flow) - 1
        self.flows.remove(self.active_flow)
        if len(self.flows) > 0:
            self.active_flow = self.flows[new_flow_idx]
        else:
            self.active_flow = None

    def plugins_save_configs(self):
        """Direct all plugins to save configuration of the plugin."""
        for p in self.plugins:
            p.save_configuration()


# ================ Client Implemented  ================
class Plugin(ABC):
    """
    Any class that inherits from this, becomes a plugin and is expected to implement the methods below.
    Only one instance of this class is expected for each plugin PER APP.
    If session/flow-instance-specific behavior is desired, the session change signal must be watched and handled.

    Required attributes:
    - name: str  # the name of the plugin
    - refreshable: bool  # if the panel and controls should be called again due to a change in widget objects
                           (only used by the app screen to determine whether to rerender this plugin)
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

    @abstractmethod
    def save_configuration(self):
        """Optional method to implement that is called by the editor when exiting."""
        pass
