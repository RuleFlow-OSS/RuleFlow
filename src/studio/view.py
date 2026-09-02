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
from textual import events
from textual.css.query import NoMatches
from textual.app import App, ComposeResult
from textual.containers import Container, Center, Horizontal, Vertical, ScrollableContainer, HorizontalGroup
from textual.screen import Screen, ModalScreen
from textual.widget import Widget
from textual.widgets import (
    DirectoryTree as _DirectoryTree, TextArea, Button, Label,
    Select, TabbedContent, OptionList, Input, SelectionList,
    Footer, ContentSwitcher, Static, Checkbox, RadioSet
)
from textual.widgets.option_list import Option, DuplicateID as DuplicateIDError
from textual import on

from studio import config
from studio import model
from core.signals import Signal  # we don't use Textual builtin signal system due to limitation with widget mounting being required first.
from lang import parser as flowlang_parser
import re


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
            if path.is_dir() or not any(map(path.match, config.HIDDEN_FILE_PATTERNS)):
                yield path


class ModalDialog(ModalScreen[dict]):
    """
    A flexible modal with border-titled inputs, notes, and dynamic buttons.
    Returns: {"pressed_button": str, "inputs": {id: value}}
    """

    def __init__(self,
                 title: str,
                 fields: list[dict] | None = None,
                 buttons: list[str] | None = None):
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
        self.query_one("#modal-dialog-submit-btn").press()  # type: ignore


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


class HorizontalSplitter(Widget):
    """A custom widget to handle click-and-drag vertical resizing."""

    DEFAULT_CSS = """
        HorizontalSplitter {
            height: 1;
            width: 100%;
            color: $text-disabled;
            background: transparent;
            content-align: center middle;
        }
        HorizontalSplitter:hover {
            color: $text;
            background: $boost;
        }
        """

    def render(self) -> str:
        """Renders a horizontal grip line in the center."""
        return "" if self.is_dragging else "⋯"

    def __init__(self, target_id: str, reverse: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_id = target_id
        self.reverse = reverse
        self.is_dragging = False
        self.start_y = 0
        self.start_height = 0

    def on_mouse_down(self, event: events.MouseDown) -> None:
        try:
            target = self.parent.query_one(f"#{self.target_id}")
            self.start_height = target.region.height
            self.start_y = event.screen_y
            self.is_dragging = True
            self.capture_mouse()
            event.stop()
        except NoMatches:
            pass

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.is_dragging:
            try:
                target = self.parent.query_one(f"#{self.target_id}")
                delta_y = event.screen_y - self.start_y

                # If target is below the splitter, dragging UP (negative delta) increases height
                if self.reverse:
                    new_height = self.start_height - delta_y
                else:
                    new_height = self.start_height + delta_y

                # Impose boundaries (e.g., minimum 5 rows, maximum 40 rows)
                new_height = max(5, min(new_height, 40))

                target.styles.height = new_height
            except NoMatches:
                pass

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self.is_dragging:
            self.release_mouse()
            self.is_dragging = False


class VerticalSplitter(Widget):
    """A custom widget to handle click-and-drag resizing of adjacent containers."""
    DEFAULT_CSS = """
        VerticalSplitter {
            width: 1;
            height: 100%;
            color: $text-disabled; /* Greys out the grip lines */
            background: transparent;
            content-align: center middle; /* Centers the grip character */
        }
        VerticalSplitter:hover {
            color: $text; /* Brightens the grip */
            background: $boost; /* Adds a very subtle, soft background highlight */
        }
        """

    def render(self) -> str:
        """Renders a vertical grip line in the center."""
        return "" if self.is_dragging else "⋮"

    def __init__(self, target_id: str, reverse: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.target_id = target_id
        self.reverse = reverse          # If the target is on the right of the splitter, we need to reverse the math
        self.is_dragging = False
        self.start_x = 0
        self.start_width = 0

    def on_mouse_down(self, event: events.MouseDown) -> None:
        """Triggered when the user clicks the splitter."""
        try:
            # self.parent ensures we grab the container strictly in the current layout scope
            target = self.parent.query_one(f"#{self.target_id}")
            self.start_width = target.region.width
            self.start_x = event.screen_x
            self.is_dragging = True
            self.capture_mouse()
            event.stop()
        except NoMatches:
            pass

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """Triggered when the user drags the mouse."""
        if self.is_dragging:
            try:
                target = self.parent.query_one(f"#{self.target_id}")
                if not target.display:
                    target.display = True
                delta_x = event.screen_x - self.start_x

                # Calculate new width based on which side the target is on
                if self.reverse:
                    new_width = self.start_width - delta_x
                else:
                    new_width = self.start_width + delta_x

                # Impose boundaries (e.g., minimum 15 columns, maximum 80 columns)
                new_width = max(15, min(new_width, 80))

                # Apply the new width via CSS injection
                target.styles.width = new_width
            except NoMatches:
                pass

    def on_mouse_up(self, event: events.MouseUp) -> None:
        """Triggered when the user releases the click."""
        if self.is_dragging:
            self.release_mouse()
            self.is_dragging = False


class EditorInstance(Widget):
    BINDINGS = [  # NOTE: hide by adding `, show=False` to a binding
        ("ctrl+s", "save_file", "Save File"),
        ("ctrl+r", "run", "Run"),
        ("shift+f1", "toggle_code_editor", "Toggle Code"),
        ("shift+f2", "toggle_panel", "Toggle Panel"),
        ("ctrl+f2", "toggle_controls", "Toggle Controls"),
    ]

    def action_run(self):
        """Action to press the run button upon this action..."""
        try: self.query_one('#toolbar-btn-exec').press()
        except NoMatches: pass

    def action_save_file(self):
        m: model.Model = self.MODEL
        m.write_file(self.code_editor_text_area.text)
        self._is_dirty = False
        self.open_file_label.update(m.file_path.name)
        # self.notify(f"Saved the \"{m.file_path.name}\" file.")

    def action_toggle_controls(self):
        menu = self.query_one("#plugin-controls")
        menu.display = not menu.display

    def action_toggle_panel(self):
        panel = self.query_one("#plugin-panel")
        panel.display = not panel.display

    def action_toggle_code_editor(self):
        panel = self.query_one("#code-editor")
        panel.display = not panel.display

    # ==== Initial Setup and Signal Connections ====
    def __init__(self, *args, file_path: Path, **kwargs):
        super().__init__(*args, **kwargs)

        # Track the dirty state to prevent unnecessary polling for the "*" prefix
        self._is_dirty: bool = False

        # ==== Signals ====
        self.sig_button_pressed: Signal[Button.Pressed] = Signal()
        self.sig_checkbox_changed: Signal[Checkbox.Changed] = Signal()
        self.sig_input_submit: Signal[Input.Changed] = Signal()
        self.sig_selection_list_toggled: Signal[SelectionList.SelectionToggled] = Signal()
        self.sig_select_changed: Signal[Select.Changed] = Signal()
        self.sig_radio_set_changed: Signal[RadioSet.Changed] = Signal()

        # ==== Model Interface ====
        self.MODEL: model.Model = model.Model(
            self.app.project_name,
            self.app.project_path,
            file_path,
            self
        )

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
        """Handle emitting the Select changed signal"""
        self.sig_select_changed.emit(event)

    @on(RadioSet.Changed)
    def _emit_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle emitting the RadioSet changed signal"""
        self.sig_radio_set_changed.emit(event)

    # ==== Composition ====
    def compose(self) -> ComposeResult:
        self.can_focus = True  # so that if all widgets are hidden, the actions (and bindings) can still work.

        # --- MIDDLE COLUMN: Workspace Panel & Editor---
        with Vertical(id="workspace"):
            # Top Toolbar
            with Horizontal(id='workspace-toolbar') as wt:
                self.workspace_toolbar: Horizontal = wt  # this way plugins can add buttons or widgets here
                self.reload_btn = Button('⟳', id='reload-file', classes='small-btn gray', tooltip='Reload', compact=True)
                self.reload_btn.can_focus = False
                yield self.reload_btn
                self.open_file_label = Label(self.MODEL.file_path.name, classes='gray')
                yield self.open_file_label
                if (_:=self.screen.selected_variant) != 'main':
                    yield Label(f' | {_}', classes='gray')
                yield Spacer()

            # Code Editor
            self.code_editor_text_area: TextArea = TextArea.code_editor(
                text=self.MODEL.read_file(),  # type: ignore
                id="code-editor",
                theme='css',
                language=config.DEFAULT_SYNTAX_HIGHLIGHTING.get(self.MODEL.file_path.suffix, None)
            )
            yield self.code_editor_text_area

            yield HorizontalSplitter(target_id="code-editor")  # TODO: fix bug weird bug where dragging sidebar size make collapsing code not work properly.

            # Plugin Panel
            with TabbedContent(id="plugin-panel"):
                # loop through the plugin TabPanes and yield them here
                for plugin in self.MODEL.plugins:
                    if _ := plugin.panel():
                        yield _

        yield VerticalSplitter(target_id="plugin-controls", reverse=True)

        # --- RIGHT COLUMN: Plugin Control Menu ---
        with Vertical(id="plugin-controls"):
            yield Label("", classes="pane-header", id="plugin-controls-header")
            with ContentSwitcher(id="sidebar-switcher"):
                # loop through the collapsable's that the plugin provides, and place in Vertical containers.
                for i, plugin in enumerate(self.MODEL.plugins):
                    with ScrollableContainer(id=f'tab-{i + 1}'):
                        for c in plugin.controls():
                            yield c

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        """Dynamically switches the Right Sidebar content AND Title to match the panel."""
        container: ContentSwitcher = self.query_one('#sidebar-switcher')
        container.current = event.pane.id  # make switch
        self.query_one('#plugin-controls-header').content = f"⭘ {event.pane._title}"

    @on(Button.Pressed, '#reload-file')
    def _hande_reload_button(self):
        self.code_editor_text_area.text = self.MODEL.read_file()
        self._is_dirty = False
        self.open_file_label.update(self.MODEL.file_path.name)

    @on(TextArea.Changed, "#code-editor")
    def _on_editor_text_changed(self, event: TextArea.Changed) -> None:
        """Fires when text changes, but only updates the UI once."""
        if self._is_dirty:
            return
        if self.MODEL.is_dirty(event.text_area.text):
            self._is_dirty = True
            self.open_file_label.update(f"*{self.MODEL.file_path.name}")


class EditorScreen(Screen):
    """
    The main IDE interface matching Image 2 with dynamic sidebar logic.
    """
    BINDINGS = [  # NOTE: hide by adding `, show=False` to a binding
        ("ctrl+f1", "toggle_project_dir", "Toggle Files")
    ]
    selected_file: DirectoryTree.FileSelected | None = None
    selected_variant: str = 'main'
    variants: list[str] = []

    def action_toggle_project_dir(self):
        sidebar = self.query_one("#project-directory")
        sidebar.display = not sidebar.display

    def compose(self) -> ComposeResult:
        # --- Project Files Panel ---
        with Vertical(id="project-directory"):
            yield Label(f"⭘ {self.app.project_name}", id="project-title-label", classes="pane-header")
            with HorizontalGroup():
                yield Label(f" Variant: ", markup=False)
                yield Select((), prompt=self.selected_variant, compact=True, id="variant-selector")
                yield Button('+', compact=True, classes='green small-btn', id="btn-add-variant")
                yield Button('-', compact=True, classes='red small-btn', id="btn-remove-variant")
            yield DirectoryTree(self.app.project_path, id="project-dir-tree")
            yield Button('↻  Refresh Directory', id='btn_refresh_project_dir', classes='full-width gray')

        yield VerticalSplitter(target_id="project-directory")

        # --- Workspace Section ---
        self.loading_label = Label('> Please select a file <', id='loading-label')
        self.editor_instance_switcher = ContentSwitcher(
            self.loading_label,
            initial="loading-label",
            id='editor-instance-switcher'
        )
        yield self.editor_instance_switcher

        # --- Footer ---
        yield Footer()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected):
        path: Path = event.path
        if not path.exists():
            self.notify("That file no longer exists!", severity="error")
            self.query_one(DirectoryTree).reload()
            return
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', path.name)
        instance_id = f"editor_{self.selected_variant.replace(' ', '-')}_{safe_name}"  # must start with something like "editor" to avoid invalid chars for id
        if self.editor_instance_switcher.query(f"#{instance_id}"):
            self.editor_instance_switcher.current = instance_id
        else:
            self.loading_label.content = f'Loading [u bold cyan]{path.name}[/] file...'
            self.editor_instance_switcher.current = 'loading-label'
            def _load_editor_instance():  # use function to perform update later so that loading screen works
                new_editor = EditorInstance(id=instance_id, file_path=path)
                self.editor_instance_switcher.mount(new_editor)
                self.editor_instance_switcher.current = instance_id
                if not new_editor.MODEL.plugins:
                    new_editor.action_toggle_controls()
                    new_editor.action_toggle_panel()
            self.set_timer(0.1, _load_editor_instance)
        self.selected_file = event

    @on(Button.Pressed, '#btn-add-variant')
    def btn_add_variant(self):

        def handle_modal_result(result: dict) -> None:
            if result["pressed_button"] == "Cancel":
                return
            variant_name: str = result["input"]["variant_name"]
            if not variant_name:
                self.notify("A new variant must be given a name!", severity="error")
                return
            if variant_name in self.variants:
                self.notify("A variant with that name already exists!", severity="error")
                return
            self.variants.append(variant_name)
            self.__refresh_variant_selector__()
            self.notify(f"Created the \"{variant_name}\" variant...")

        # Push the screen with the configuration and callback
        self.app.push_screen(
            ModalDialog(
                title="Create Variant",
                fields=[
                    {
                        "type": "note",
                        "text": "Project variants are a temporary (per-session) way to open multiple versions of the same file(s), enabling parallel editing and exploration."
                    },
                    {
                        "type": "input",
                        "prompt": "Variant Name",
                        "placeholder": "e.g. version 2",
                        "id": "variant_name"
                    }
                ],
                buttons=["Create", "Cancel"]
            ),
            callback=handle_modal_result
        )

    @on(Button.Pressed, '#btn-remove-variant')
    def btn_remove_variant(self):
        if self.selected_variant == 'main':
            self.notify("The main variant cannot be removed!", severity="error")
            return

        def handle_modal_result(result: dict):
            if result.get("pressed_button") == "Continue":
                self.notify(f"Deleted the \"{self.selected_variant}\" variant...")
                self.variants.remove(self.selected_variant)
                self.__refresh_variant_selector__()

        self.app.push_screen(
            ModalDialog(
                title="Remove Variant?",
                fields=[
                    {
                        "type": "note",
                        "text": "Please confirm variant removal..."
                    }
                ],
                buttons=["Continue", "Cancel"]
            ),
            callback=handle_modal_result
        )

    def __refresh_variant_selector__(self) -> None:
        """Helper to refresh the variant selector."""
        ol: Select = self.query_one("#variant-selector")
        ol.set_options([(f, i) for i, f in enumerate(self.variants)])
        self.selected_variant = 'main'

    @on(Select.Changed, '#variant-selector')
    def select_variant(self, event: Select.Changed):
        if isinstance(event.value, int):
            self.selected_variant = self.variants[event.value]
        else:
            self.selected_variant = 'main'
        if self.selected_file:
            self.post_message(self.selected_file)

    @on(Button.Pressed, '#btn_refresh_project_dir')
    def btn_refresh_project_dir(self):
        self.query_one(DirectoryTree).reload()
        self.notify(f"Project directory was refreshed.")


class Main(App):
    project_name: str = ''
    project_path: Path = Path()
    sig_exiting_studio: Signal = Signal()

    CSS_PATH = "styles.tcss"

    def on_mount(self):
        # create the screens and push the welcome page
        self.install_screen(WelcomeScreen(), name="welcome")
        self.install_screen(EditorScreen(), name="editor")
        def on_project_opened(result: dict):
            self.project_name = result["project_name"]
            self.project_path = result["project_path"]
            flowlang_parser.set_working_dir(self.project_path)  # so that mmacros work nicely.
            self.push_screen("editor")
            self.theme = 'rose-pine'
        self.push_screen("welcome", callback=on_project_opened)

    def action_quit(self):
        if isinstance(self.screen, WelcomeScreen):
            self.exit()
        def handle_modal_result(result: dict):
            if result["pressed_button"] == "Yes":
                self.screen.action_save_file()
                if result["checkbox"]["save_config"]["value"]:
                    self.sig_exiting_studio.emit()
                self.exit()
        # Push the screen with the configuration and callback
        self.app.push_screen(
            ModalDialog(
                title="Exit RuleFlow Studio?",
                fields=[
                    {
                        "type": "note",
                        "text": "Are you sure want to exit ruleflow studio? Don't forget to save you workflow if necessary.",
                    },
                    {
                        "type": "checkbox",
                        "label": "Let plugins cleanup",
                        "initial": True,
                        "id": "save_config"
                    }
                ],
                buttons=["Yes", "No"]
            ),
            callback=handle_modal_result
        )


if __name__ == "__main__":
    app = Main()
    app.run()
