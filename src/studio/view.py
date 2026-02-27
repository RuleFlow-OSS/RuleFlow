"""View/Controller side of the MVC paradigm

Policies:
- For software design reasons, it is best to make the user-flow from welcome screen to editor irreversible for the
current process so that we don't have to introspectively modify state if the user selects a different project.
This decision was made due to the ease of plugin implementation and project saving.
"""
from pathlib import Path
from typing import cast, Iterable
from textual.app import App, ComposeResult
from textual.containers import Container, Center, Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    DirectoryTree as _DT, TextArea, Button, Label,
    Select, TabbedContent, OptionList, Input,
    Footer, ContentSwitcher, Static, Checkbox
)
from textual.widgets.option_list import Option, DuplicateID as DuplicateIDError
from textual import on
from studio import config
from studio import model


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


class DirectoryTree(_DT):
    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        for path in paths:
            if str(path).endswith("__") or str(path).startswith("__"):
                continue
            if path.is_dir() or any(map(path.match, config.SUPPORTED_FILE_TYPES)):
                yield path


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
            self.app.MODEL = model.Model(  # create an instance of model side of the MVC design
                i.id,  # we use id as the field to store the name of the project
                config.RecentProjects.get_path(i.id)
            )
            self.app.push_screen("editor")
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

    def __refresh_flow_selector__(self) -> None:
        """Call to refresh the flow selector"""
        # load flows
        m: model.Model = self.app.MODEL
        ol: Select = self.query_one("#select-flow")
        ol.set_options([(f.name, i) for i, f in enumerate(m.flows)])
        try:
            # noinspection PyProtectedMember
            ol._init_selected_option(m.flows.index(m.active_flow))  # select the first option
        except: pass

    def __refresh_plugin_components__(self) -> None:
        pass

    def on_mount(self) -> None:
        self.__refresh_flow_selector__()
        self.__refresh_plugin_components__()

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
                yield Label("▼ ", classes='gray')
                yield Select((), id="select-flow", compact=True)
                yield Button('+', id="btn-add-flow", compact=True, classes='increment-btn green')
                yield Button('-', id="btn-sub-flow", compact=True, classes='increment-btn red')
                yield Spacer()
                # yield Label("No Open File", classes='gray')
                # yield Spacer()
                yield Button("Run", id="btn-run", classes="action-btn green", compact=True)
                yield Label("|", classes="separator")
                yield Button("Debug", id="btn-debug", classes="action-btn orange", compact=True)
                yield Label("|", classes="separator")
                yield Button("Clear", id="btn-clear", classes="action-btn red", compact=True)

            # Code Editor
            yield (_:=TextArea.code_editor(
                text="// Select a .flow file to begin...",
                id="code-editor",
                disabled=True
            ))
            # _.register_language()

            # Plugin Panel
            with TabbedContent(id="plugin-panel"):
                # loop through the plugin TabPanes and yield them here
                pass

        # --- RIGHT COLUMN: Plugin Control Menu ---
        with Vertical(id="plugin-controls"):
            yield Label("⭘ Run Settings", classes="pane-header", id="plugin-controls-header")
            with ContentSwitcher(id="sidebar-switcher"):
                # loop through the collapsable's that the plugin provides, and place in Vertical containers.
                pass

        # --- Footer ---
        yield Footer()

    # --- ACTION HANDLERS ---
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

    # ==== Top Bar ====
    @on(Button.Pressed, '#btn-add-flow')
    def btn_add_flow(self):
        def handle_modal_result(result: dict) -> None:
            if result["pressed_button"] == "Cancel":
                return
            if not result["input"]["flow_name"]:
                self.notify("A new flow must be given a name!", severity="error")
                return
            if not self.app.MODEL.create_new_flow(result["input"]["flow_name"], result["checkbox"]["branch_checkbox"]):
                self.notify(f"A flow with name \"{result["input"]["flow_name"]}\" already exists.", severity="error")
                return
            self.__refresh_flow_selector__()
            self.notify(f"Created the \"{self.app.MODEL.active_flow.name}\" flow session...")

        # Push the screen with the configuration and callback
        self.app.push_screen(
            ModalDialog(
                title="Flow Creation Tool",
                fields=[
                    {
                        "type": "note",
                        "text": "Create a new flow session and optionally branch it from the current flow session."
                    },
                    {
                        "type": "input",
                        "prompt": "New Flow Name",
                        "placeholder": "e.g. Flow1",
                        "id": "flow_name"
                    },
                    {
                        "type": "checkbox",
                        "label": "Branch from current flow session",
                        "id": "branch_checkbox",
                    }
                ],
                buttons=["Create", "Cancel"]
            ),
            callback=handle_modal_result
        )

    @on(Button.Pressed, '#btn-sub-flow')
    def btn_remove_flow(self):
        if not self.app.MODEL.active_flow:
            self.notify("Empty flow sessions!", severity="error")
            return
        def handle_modal_result(result: dict):
            if result.get("pressed_button") == "Yes":
                self.notify(f"Deleted the \"{self.app.MODEL.active_flow.name}\" flow session...")
                self.app.MODEL.delete_selected_flow()
                self.__refresh_flow_selector__()
        self.app.push_screen(
            ModalDialog(
                title="Delete Flow?",
                fields=[
                    {
                        "type": "note",
                        "text": "Please confirm flow deletion..."
                    }
                ],
                buttons=["Yes", "No", "Cancel"]
            ),
            callback=handle_modal_result
        )

    @on(Select.Changed, '#select-flow')
    def select_flow(self, event: Select.Changed):
        if isinstance(event.value, int):
            self.app.MODEL.active_flow = self.app.MODEL.flows[event.value]

    @on(Button.Pressed, "#btn-clear")
    def btn_clear(self):
        pass

    @on(Button.Pressed, "#btn-debug")
    def btn_debug(self):
        pass

    @on(Button.Pressed, "#btn-run")
    def action_run(self):
        pass

    # ==== Panel and Controls ====
    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated):
        """Dynamically switches the Right Sidebar content AND Title."""
        pass

    # ==== File Manager ====
    @on(Button.Pressed, '#btn_refresh_project_dir')
    def btn_refresh_project_dir(self):
        dir_tree: DirectoryTree = self.query_one("#project-dir-tree")
        dir_tree.reload()
        self.notify(f"Refreshed Project Directory...")


class Main(App):
    CSS_PATH = "styles.tcss"

    def on_mount(self):
        # create the screens and push the welcome page
        self.install_screen(WelcomeScreen(), name="welcome")
        self.install_screen(EditorScreen(), name="editor")
        self.push_screen("welcome")

    def action_quit(self):
        if not hasattr(self, "MODEL"):
            self.exit()
        def handle_modal_result(result: dict):
            if result["pressed_button"] == "Yes":
                if result["checkbox"]["save_config"]["value"]:
                    self.app.MODEL.plugins_save_configs()
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
    import textual.events
    app = Main()
    app.run()
