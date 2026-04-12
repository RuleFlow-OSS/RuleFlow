"""View/Controller side of the MVC paradigm

LongTermTODO:
- Make each flow session have its own text editor.
- Add edit buttons create, rename, and delete files.

Policies:
- For software design reasons, it is best to make the user-flow from welcome screen to editor irreversible for the
current process so that we don't have to introspectively modify state if the user selects a different project.
This decision was made due to the ease of plugin implementation and project saving. At some point, however, we may
prefer to have a checkbox called exit to project manager when ctrl+q is pressed.
"""
from pathlib import Path
from typing import cast, Iterable
from textual.app import App, ComposeResult
from textual.containers import Container, Center, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    DirectoryTree as _DirectoryTree, TextArea as _TextArea, Button, Label,
    Select, TabbedContent, OptionList, Input, SelectionList,
    Footer, ContentSwitcher, Static, Checkbox
)
from textual.widgets.option_list import Option, DuplicateID as DuplicateIDError
from textual import on
from studio import config
from studio import model
from core.signals import Signal  # we don't use Textual builtin signal system due to limitation with widget mounting being required first.


LOGO: str = r"""______      _     ______ _                    _____ _             _ _       
| ___ \    | |    |  ___| |                  /  ___| |           | (_)      
| |_/ /   _| | ___| |_  | | _____      __    \ `--.| |_ _   _  __| |_  ___  
|    / | | | |/ _ \  _| | |/ _ \ \ /\ / /     `--. \ __| | | |/ _` | |/ _ \ 
| |\ \ |_| | |  __/ |   | | (_) \ V  V /     /\__/ / |_| |_| | (_| | | (_) |
\_| \_\__,_|_|\___\_|   |_|\___/ \_/\_/      \____/ \__|\__,_|\__,_|_|\___/"""


class Spacer(Static):
    """Spacer widget to take up as much horizontal space as possible."""
    def __init__(self):
        super().__init__()
        self.styles.width = '1fr'  # make it take up as much space as possible


class DirectoryTree(_DirectoryTree):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        for path in paths:
            if str(path.stem) == 'plugins' or str(path).endswith("__") or str(path).startswith("__"):
                continue
            if path.is_dir() or any(map(path.match, config.SUPPORTED_FILE_TYPES)):
                yield path


class TextArea(_TextArea):
    def load_text(self, text: str | None) -> None:
        """Overrides the load_text method so that placeholders work properly..."""
        # NOTE: edit history is cleared
        if text is None:
            super().load_text("")
            self.disabled = True
            self.placeholder = "// Select a .flow file to begin..."
            return
        if self.disabled: self.disabled = False
        super().load_text(text)
        self.placeholder = f"// This file is empty!\n// Start typing to edit this file..."


# import re
# class CustomHighlightTextArea(TextArea):
#     # 1. Define your custom highlighting rules as (regex_pattern, highlight_name)
#     # The 'highlight_name' should match standard names used in Textual themes
#     # (e.g., "keyword", "string", "comment", "number", "variable", "function").
#     HIGHLIGHT_RULES = [
#         (r"\b(def|class|return|if|else|elif|import|from)\b", "keyword"),
#         (r'".*?"|\'.*?\'', "string"),
#         (r"#.*", "comment"),
#         (r"\b\d+\b", "number"),
#         (r"\b[A-Z][a-zA-Z0-9_]*\b", "type"),  # Class names
#     ]
#
#     def on_mount(self) -> None:
#         # Pre-compile the regexes for performance when the widget mounts
#         self._compiled_rules = [
#             (re.compile(pattern), name)
#             for pattern, name in self.HIGHLIGHT_RULES
#         ]
#
#     def _build_highlight_map(self) -> None:
#         """Override to apply custom regex-based highlights instead of tree-sitter."""
#
#         # 1. Clear the existing line cache and highlight map
#         self._line_cache.clear()
#         self._highlights.clear()
#
#         # 2. Iterate over every line in the document
#         for line_index in range(self.document.line_count):
#             line_text = self.document[line_index]
#
#             # 3. Apply each regex rule to the current line
#             for regex, highlight_name in self._compiled_rules:
#                 for match in regex.finditer(line_text):
#                     # 4. CRITICAL: Convert Python's character indices to byte offsets.
#                     # Textual's `_render_line` expects byte offsets because that is
#                     # what Tree-sitter natively outputs.
#                     start_char, end_char = match.span()
#                     start_byte = len(line_text[:start_char].encode("utf-8"))
#                     end_byte = len(line_text[:end_char].encode("utf-8"))
#
#                     # 5. Append the highlight tuple for this line
#                     self._highlights[line_index].append(
#                         (start_byte, end_byte, highlight_name)
#                     )


class ModalDialog(ModalScreen[dict]):
    """
    A flexible modal with border-titled inputs, notes, and dynamic buttons.
    Returns: {"pressed_button": str, "inputs": {id: value}}
    """

    def __init__(self,
                 title: str,
                 fields: list[dict] = None,
                 buttons: list[str] = None):
        super().__init__()
        self.title_text = title
        self.fields_config = fields or []
        self.buttons_config = buttons or ["OK"]

    def compose(self) -> ComposeResult:
        with Vertical(id="modal-dialog"):
            yield Label(self.title_text, id="modal-title")

            with Vertical(id="modal-content-container"):
                for cfg in self.fields_config:
                    field_type = cfg.get("type", "input")

                    if field_type == "note":
                        yield Static(cfg.get("text", ""), classes="modal-note")

                    elif field_type == "input":
                        ipt = Input(
                            placeholder=cfg.get("placeholder", ""),
                            id=cfg.get("id"),
                            password=cfg.get("password", False),
                            value=cfg.get("initial")
                        )
                        # Set the prompt as the border title
                        ipt.border_title = cfg.get("prompt", "")
                        yield ipt

                    elif field_type == "checkbox":
                        yield Checkbox(
                            label=cfg.get("label", ""),
                            value=cfg.get("initial", False),
                            id=cfg.get("id")
                        )
                    # Maybe add SelectionList support at some point
                    pass

            with Horizontal(id="modal-buttons"):
                for index, btn_text in enumerate(self.buttons_config):
                    yield Button(
                        btn_text,
                        variant="primary" if index == 0 else "default",
                        name=btn_text,
                        id="modal-dialog-submit-btn" if index == 0 else None
                    )

    def on_button_pressed(self, event: Button.Pressed):
        # Package the state of all inputs and the button identity
        results = {
            "pressed_button": event.button.name,
            "input": {
                ipt.id: ipt.value for ipt in self.query(Input) if ipt.id
            },
            "checkbox": {
                chk.id: chk.value for chk in self.query(Checkbox) if chk.id
            }
        }
        self.dismiss(results)

    def on_input_submitted(self):
        # noinspection PyUnresolvedReferences
        self.query_one("#modal-dialog-submit-btn").press()


class WelcomeScreen(Screen):
    """The main welcome screen where projects are managed."""

    def compose(self) -> ComposeResult:
        with Container(id="welcome-container") as wc:
            wc.border_subtitle = config.VERSION
            with Center():  # to center it *relative* to the other widgets
                yield Label(LOGO, id="welcome-title")
            yield (
                _:=OptionList(id="recents-list")
            )
            _.border_title = 'Recent Projects'
            for k, v in config.RecentProjects.list().items():
                _.add_option(Option(f'{k} [grey]({v})[/grey]', k))
            with Horizontal(id="welcome-buttons"):
                yield Button("📂 Open", id="btn-open-project", variant="primary")
                yield Button("➕ New", id="btn-new-project", variant="default")
                yield Spacer()
                yield Button("🗑  Forget", id="btn-remove-recent", variant="default")

    @on(Button.Pressed, "#btn-new-project")
    def btn_new_project(self):
        """Calls the UniversalModal to get a new project path."""

        def handle_modal_result(result: dict):
            if result["pressed_button"] != "Create":
                return
            inputs = result.get("input", {})
            name = inputs.get("project_name", "").strip()
            path = inputs.get("project_path", "").strip()
            if not path or not name:
                self.notify("Both a name and project path must be provided.", severity="error")
                return
            if not Path(path).is_dir():
                self.notify('Please enter a valid path to a directory.', severity='error')
                return
            try:
                # noinspection PyUnresolvedReferences
                self.query_one("#recents-list").add_option(Option(f'{name} [grey]({path})[/grey]', name))
                config.RecentProjects.add(name, path)
                self.notify(f"Loaded project at: {path}")
            except DuplicateIDError:
                self.notify(f"That name has already been reserved!", severity="error")

        # Push the screen with the configuration and callback
        self.app.push_screen(
            ModalDialog(
                title="New Project",
                fields=[
                    {
                        "id": "project_name",
                        "prompt": "Name",
                        "placeholder": "Call it something memorable. Or don’t.",
                    },
                    {
                        "type": "note",
                        "text": "Please provide the absolute path for your new workspace."
                    },
                    {
                        "id": "project_path",
                        "prompt": "Path",
                        "placeholder": "/users/name/projects/my-project",
                    }
                ],
                buttons=["Create", "Cancel"]
            ),
            callback=handle_modal_result
        )

    @on(Button.Pressed, "#btn-open-project")
    def btn_open_project(self):
        _: OptionList = cast(OptionList, self.query_one("#recents-list"))
        if i:=_.highlighted_option:
            self.dismiss(
                {
                    "project_name": i.id,
                    "project_path": config.RecentProjects.get_path(i.id)
                }
            )
        else:
            self.notify('Please select a project to open!', severity='warning')

    @on(Button.Pressed, "#btn-remove-recent")
    def btn_remove_recent(self):
        _: OptionList = cast(OptionList, self.query_one("#recents-list"))
        if i:=_.highlighted_option:
            _.remove_option(i.id)
            config.RecentProjects.remove(i.id)
        else:
            self.notify('There is no selection to remove!', severity='warning')


# noinspection PyTypeChecker
# noinspection PyUnresolvedReferences
class EditorScreen(Screen):
    """
    The main IDE interface matching Image 2 with dynamic sidebar logic.
    """
    BINDINGS = [  # NOTE: hide by adding `, show=False` to a binding
        ("ctrl+s", "save_file", "Save File"),
        ("ctrl+r", "run", "Run"),
        ("ctrl+f1", "toggle_left_sidebar", "Toggle Left"),
        ("ctrl+f2", "toggle_right_sidebar", "Toggle Right"),
        ("shift+f1", "toggle_code_editor", "Toggle Code"),
        ("shift+f2", "toggle_bottom_panel", "Toggle Panel"),
        ("ctrl+shift+f1", "toggle_max", "Toggle Max"),
    ]

    def compose(self) -> ComposeResult:
        # --- LEFT COLUMN: Project Files ---
        with Vertical(id="project-directory"):
            yield Label(f"⭘ {self.app.MODEL.project_name}", id="project-title-label", classes="pane-header")
            yield DirectoryTree(self.app.MODEL.project_path, id="project-dir-tree")
            yield Button('↻  Refresh Directory', id='btn_refresh_project_dir', classes='full-width gray')

        # --- MIDDLE COLUMN: Workspace ---
        with Vertical(id="workspace"):
            # Top Toolbar
            with Horizontal(id='workspace-toolbar'):
                self.open_file_label = Label("No Open File", classes='gray')
                yield self.open_file_label
                yield Spacer()
                yield Button("Run", id="btn-run", classes="action-btn green", compact=True)
                yield Label("| ", classes="gray")
                yield Button("Undo", id="btn-undo", classes="action-btn orange", compact=True)
                yield Label("| ", classes="gray")
                yield Button("clear", id="btn-clear", classes="action-btn red", compact=True)

            # Code Editor
            self.code_editor_text_area: TextArea = TextArea.code_editor(
                text="",
                id="code-editor",
                disabled=True
            )
            yield self.code_editor_text_area
            # _.register_language()

            # Plugin Panel
            with TabbedContent(id="plugin-panel"):
                # loop through the plugin TabPanes and yield them here
                for plugin in self.app.MODEL.plugins:
                    if _:=plugin.panel():
                        yield _

        # --- RIGHT COLUMN: Plugin Control Menu ---
        with Vertical(id="plugin-controls"):
            yield Label("", classes="pane-header", id="plugin-controls-header")
            with ContentSwitcher(id="sidebar-switcher"):
                # loop through the collapsable's that the plugin provides, and place in Vertical containers.
                for i, plugin in enumerate(self.app.MODEL.plugins):
                    with ScrollableContainer(id=f'tab-{i+1}'):
                        for c in plugin.controls():
                            yield c

        # --- Footer ---
        yield Footer()

    # ==== Panel and Controls ====
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        """Dynamically switches the Right Sidebar content AND Title."""
        container: ContentSwitcher = self.query_one('#sidebar-switcher')
        container.current = event.pane.id
        # noinspection PyProtectedMember
        self.query_one('#plugin-controls-header').content = f"⭘ {event.pane._title}"

    # ==== File Manager ====
    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        m: model.Model = self.app.MODEL
        if not event.path.exists():
            self.notify("That file no longer exists!", severity="error")
            self.query_one(DirectoryTree).reload()
            return
        self.action_save_file()
        m.open_file(event.path)
        self.code_editor_text_area.text = m.read_file()
        self.open_file_label.content = event.path.name

    @on(Button.Pressed, '#btn_refresh_project_dir')
    def btn_refresh_project_dir(self):
        self.query_one(DirectoryTree).reload()
        self.notify(f"Refreshed Project Directory...")

    # ==== Action Handlers ====
    def action_run(self):
        """Action to press the run button upon this action..."""
        self.query_one('#btn-run').press()

    def action_save_file(self):
        m: model.Model = self.app.MODEL
        if m.write_file(self.code_editor_text_area.text):
            self.notify(f"Saved the \"{m.flow_path.name}\" file.")

    def action_toggle_left_sidebar(self):
        sidebar = self.query_one("#project-directory")
        sidebar.display = not sidebar.display

    def action_toggle_right_sidebar(self):
        menu = self.query_one("#plugin-controls")
        menu.display = not menu.display

    def action_toggle_bottom_panel(self):
        panel = self.query_one("#plugin-panel")
        panel.display = not panel.display

    def action_toggle_code_editor(self):
        panel = self.query_one("#code-editor")
        panel.display = not panel.display

    def action_toggle_max(self):
        if not self.focused:  # if nothing is focused
            return
        if self.focused.is_in_maximized_view:
            self.minimize()
        else:
            self.maximize(self.focused)

    # ==== Initial Setup and Signal Connections ====
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # ==== Signals ====
        self.sig_button_pressed: Signal[Button.Pressed] = Signal()
        self.sig_checkbox_changed: Signal[Checkbox.Changed] = Signal()
        self.sig_input_submit: Signal[Input.Changed] = Signal()
        self.sig_selection_list_toggled: Signal[SelectionList.SelectionToggled] = Signal()
        self.sig_select_changed: Signal[Select.Changed] = Signal()
        self.sig_save_config_directive: Signal = Signal()

    @on(Button.Pressed)
    def _emit_button_signals(self, event: Button.Pressed) -> None:
        """Handle emitting the button pressed signal"""
        self.sig_button_pressed.emit(event)

    @on(Checkbox.Changed)
    def _emit_checkbox_signals(self, event: Checkbox.Changed) -> None:
        """Handle emitting the checkbox changed signal"""
        self.sig_checkbox_changed.emit(event)

    @on(Input.Submitted)
    def _emit_input_submit_signals(self, event: Input.Changed) -> None:
        """Handle emitting the input changed signal"""
        self.sig_input_submit.emit(event)

    @on(SelectionList.SelectionToggled)
    def _emit_selection_list_toggled(self, event: SelectionList.SelectionToggled) -> None:
        """Handle emitting the selection list toggled signal"""
        self.sig_selection_list_toggled.emit(event)

    @on(Select.Changed)
    def _emit_select_changed(self, event: Select.Changed) -> None:
        """Handle emitting the select changed signal"""
        self.sig_select_changed.emit(event)


class Main(App):
    CSS_PATH = "styles.tcss"

    @property
    def editor_screen(self) -> EditorScreen:
        return cast(EditorScreen, self.get_screen('editor'))

    def on_mount(self):
        # create the screens and push the welcome page
        self.install_screen(WelcomeScreen(), name="welcome")
        self.install_screen(EditorScreen(), name="editor")
        def on_project_opened(result: dict):
            self.MODEL = model.Model(
                result["project_name"],
                result["project_path"],
                self.editor_screen
            )
            self.push_screen("editor")
        self.push_screen("welcome", callback=on_project_opened)

    def action_quit(self):
        if not hasattr(self, "MODEL"):
            self.exit()
        def handle_modal_result(result: dict):
            if result["pressed_button"] == "Yes":
                # noinspection PyUnresolvedReferences
                self.screen.action_save_file()
                if result["checkbox"]["save_config"]["value"]:
                    # noinspection PyTypeChecker
                    self.editor_screen.sig_save_config_directive.emit()
                self.exit()
        # Push the screen with the configuration and callback
        self.app.push_screen(
            ModalDialog(
                title="Exit RuleFlow Studio?",
                fields=[
                    {
                        "type": "note",
                        "text": "Saving the plugin configuration directs all plugins to save their settings (if supported)."
                    },
                    {
                        "type": "checkbox",
                        "label": "Save plugin configuration",
                        "id": "save_config"
                    }
                ],
                buttons=["Yes", "No", "Cancel"]
            ),
            callback=handle_modal_result
        )


if __name__ == "__main__":
    app = Main()
    app.run()
