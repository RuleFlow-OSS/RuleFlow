"""The model side of the MVC paradigm"""
from typing import Optional, Iterator, TYPE_CHECKING, cast, Callable
from lang import FlowLangBase, FlowLang  # in the implementation
from abc import ABC, abstractmethod
from textual.widgets import TabPane
from textual.widget import Widget

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


class Model:
    """
    The source of truth for the application state (a Singleton Pattern).
    Manages the current workspace and open file flows.
    """

    def __init__(self, name: str, project_path: Path, view: EditorScreen) -> None:
        """Name and project path are passed to initiate the model. The textual app is simply passed as a reference so
        that plugins maintain access to it."""
        # ======== Project Attributes ========
        self.project_name: str = name  # name the user has given the project
        self.project_path: Path = project_path
        self.flow_path: Path | None = None
        self._edit_hash: int = 0  # used to check if some text has already been saved...
        self.flow: FlowLangBase = FlowLang()

        # ======== View Hook (for access through model/plugin) ========
        self.view: EditorScreen = view

        # ======== Plugins ========
        self.plugins: list[Plugin] = []

        # add builtin plugins
        from studio.stdplgns import run, explore, analysis
        for module in (run, explore, analysis):
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

        # ======== Initialize any children models (plugins) ========
        for p in self.plugins:
            p.on_initialized()

    def write_file(self, text: str) -> bool:
        """Writes to the file and returns True if the file was written to."""
        if self.flow_path and self._edit_hash != (eh:=hash(text)):
            self.flow_path.write_text(text)
            self._edit_hash = eh
            return True
        return False

    def read_file(self) -> str | None:
        if self.flow_path:
            self._edit_hash = hash(text:=self.flow_path.read_text())
            return text
        return None

    def open_file(self, path: Path | None):
        self.flow_path = path


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
