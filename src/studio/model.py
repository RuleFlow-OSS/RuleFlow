"""The model side of the MVC paradigm"""
from typing import Iterator, TYPE_CHECKING, cast, Callable, Sequence, Any
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
    from studio.view import EditorInstance as View
else:
    class View(object): pass  # must define due to reference in type casting


class Model:
    """
    The source of truth for the application state (specific to each file, and thus editor instance).
    """

    def __init__(self, project_name: str, project_path: Path, file_path: Path, view: View) -> None:
        """Name and project path are passed to initiate the model. The textual app is simply passed as a reference so
        that plugins maintain access to it."""
        # ======== Project Attributes ========
        self.project_name: str = project_name  # name the user has given the project
        self.project_path: Path = project_path
        self.file_path: Path = file_path
        self._edit_hash: int = 0  # used to check if some text has already been saved...
        self.data: dict[str, Any] = {}  # this is where model data can be stored (such as the Flow(s) instance)

        # ======== Plugins ========
        self.plugins: list[Plugin] = []

        def grab_plugins(m):  # a function to grab Plugin subclasses from modules
            for _, obj in inspect.getmembers(m, inspect.isclass):
                if issubclass(obj, Plugin) and obj is not Plugin and not inspect.isabstract(obj):
                    file_type: str = self.file_path.suffix
                    if hasattr(obj, 'exclude_file_types') and file_type in obj.file_types:
                        continue
                    if hasattr(obj, 'file_types') and file_type not in obj.file_types:
                        continue
                    self.plugins.append(obj(self, view))

        # add builtin plugins
        from studio.stdplgns import run, explore, analysis
        for module in (run, explore, analysis):
            grab_plugins(module)

        # load all plugins classes
        for pp in (self.project_path / "plugins").glob("*.py"):
            module_name = f"plugins.{pp.stem}"  # make it appear as if it lives in a package called plugins.
            # Dynamically import module
            spec = importlib.util.spec_from_file_location(module_name, pp)  # tells Python how to load the file
            module = importlib.util.module_from_spec(spec)  # allocates module object
            sys.modules[module_name] = module  # makes it importable and unique
            spec.loader.exec_module(module)  # populates module with code and objects
            grab_plugins(module)

        # ======== Initialize the controllers (plugins) ========
        for p in self.plugins:
            p.on_initialized()

    def write_file(self, text: str) -> bool:
        """Writes to the file and returns True if the file was written to."""
        if self.file_path and self._edit_hash != (eh:=hash(text)):
            self.file_path.write_text(text)
            self._edit_hash = eh
            return True
        return False

    def read_file(self) -> str | None:
        """Read in the contents of a file."""
        if self.file_path:
            self._edit_hash = hash(text:=self.file_path.read_text())
            return text
        return None

    def is_dirty(self, text: str):
        return self._edit_hash != hash(text)


# ================ Plugin Support ================
class Plugin(ABC):
    """
    Any class that inherits from this, becomes a plugin and is expected to implement the methods below.
    Only one instance of this class is expected for each plugin PER FLOW.
    If session/flow-instance-specific behavior is desired, the session change signal must be watched and handled.

    IMPORTANT NOTE: The view call self.panel() and then self.control() in that order. Thus, calls may need to be placed
    strategically if self.panel() references something in self.controls().

    Required attributes:
    - name: str  # the name of the plugin
    - file_types: list[str]  # the list of files that are supported.
    - model: Model  # gives the plugin access to the model
    - view: View  # gives the plugin access to the app
    """
    name: str = cast(str, cast(object, None))
    file_types: Sequence[str] = []

    def __init__(self, model: Model, view: View) -> None:
        # Define the unset required attributes
        self._model: Model = model
        self._view: View = view

    @property
    def model(self) -> Model:
        return self._model

    @property
    def view(self) -> View:
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
