"""The model side of the MVC paradigm"""
from typing import Optional, Iterator, TYPE_CHECKING, cast, Callable
from lang import FlowLangBase, FlowLang  # in the implementation
from abc import ABC, abstractmethod
from textual.widgets import TabPane
from textual.widget import Widget
from copy import deepcopy

# used for dynamic imports and path management
from pathlib import Path
import importlib.util
import inspect
import sys
import importlib

# used for type checking
if TYPE_CHECKING:
    from studio.view import EditorScreen
else:
    class EditorScreen(object): pass  # must define due to reference in type casting


class Flow:
    """
    Represents a flow instance session (includes API for interacting with .flow files on the disc).
    """
    def __init__(self) -> None:
        # Metadata
        self.name: str = ""
        self.file_path: Path | None = None
        self._edit_hash: int = 0  # used to check if some text has already been saved...

        # Flow State
        self.flow: FlowLangBase = FlowLang()

    def write_file(self, text: str) -> bool:
        """Writes to the file and returns True if the file was written to."""
        if self.file_path and self._edit_hash != (eh:=hash(text)):
            self.file_path.write_text(text)
            self._edit_hash = eh
            return True
        return False

    def read_file(self) -> str | None:
        if self.file_path:
            self._edit_hash = hash(text:=self.file_path.read_text())
            return text
        return None

    def open_file(self, path: Path | None):
        self.file_path = path


class Model:
    """
    The source of truth for the application state (a Singleton Pattern).
    Manages the current workspace and open file flows.
    """

    def __init__(self, name: str, project_path: Path, view: EditorScreen) -> None:
        """Name and project path are passed to initiate the model. The textual app is simply passed as a reference so
        that plugins maintain access to it."""
        # ======== Basic Project Config ========
        self.project_name: str = name  # name the user has given the project
        self.project_path: Path = project_path

        # ======== View Hook ========
        self.view: EditorScreen = view

        # ======== Plugins ========
        self.plugins: list[Plugin] = []

        # add builtin plugins
        from studio.stdplgns import run, output, analysis
        for module in (run, output, analysis):
            for _, obj in inspect.getmembers(module):
                if isinstance(obj, Plugin):
                    obj._model = self
                    obj._view = self.view
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
                    obj._model = self
                    obj._view = self.view
                    self.plugins.append(obj)

        # ======== Active Flows ========
        self.flows: list[Flow] = []
        self.active_flow: Optional[Flow] = None

        # add default flow
        self.flows.append(_:=Flow())
        _.name = "Root"
        self.active_flow = _

        # ======== Initialize any children models (plugins) ========
        for p in self.plugins:
            p.on_initialized()

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


# ================ Plugin Support ================
class Plugin(ABC):
    """
    Any class that inherits from this, becomes a plugin and is expected to implement the methods below.
    Only one instance of this class is expected for each plugin PER APP.
    If session/flow-instance-specific behavior is desired, the session change signal must be watched and handled.

    IMPORTANT NOTE: The view call self.panel() and then self.control() in that order. Thus, calls may need to be placed
    strategically if self.panel() references something in self.controls().

    Required attributes:
    - name: str  # the name of the plugin
    - model: Model  # gives the plugin access to the model
    - view: EditorScreen  # gives the plugin access to the app
    """

    def __init__(self) -> None:
        # Define the unset required attributes
        self.name: str = cast(str, cast(object, None))
        self._model: Model = cast(Model, cast(object, None))
        self._view: EditorScreen = cast(EditorScreen, cast(object, None))

    @property
    def model(self) -> Model:
        return self._model

    @property
    def view(self) -> EditorScreen:
        return self._view

    @property
    def cft(self) -> Callable:
        """Used to call a textual method/function from another thread (for thread-safety)."""
        return self._view.app.call_from_thread

    @abstractmethod
    def on_initialized(self) -> None:
        """Called when the plugin is fully loaded by the model."""
        pass

    @abstractmethod
    def controls(self) -> Iterator[Widget]:
        """Returns the controls (in renderable format) for modifying this plugin's behavior."""
        pass

    @abstractmethod
    def panel(self) -> TabPane | None:
        """Returns the widget to be displayed in the panel for this plugin."""
        return None
