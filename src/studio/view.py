"""View/Controller side of the MVC paradigm"""
from typing import cast
from textual.app import App, ComposeResult
from textual.containers import Container, Center, Horizontal, Vertical
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    DirectoryTree, TextArea, Button, Label,
    Select, TabbedContent, OptionList, Input,
    Footer, ContentSwitcher, Static
)
from textual.widgets.option_list import Option
from textual import on
from studio import config


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


class ModalDialog(ModalScreen[dict]):
    """
    A flexible modal with border-titled inputs, notes, and dynamic buttons.
    Returns: {"button_pressed": str, "inputs": {id: value}}
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
                            value=str(cfg.get("initial", ""))
                        )
                        # Set the prompt as the border title
                        ipt.border_title = cfg.get("prompt", "")
                        yield ipt

            with Horizontal(id="modal-buttons"):
                for index, btn_text in enumerate(self.buttons_config):
                    yield Button(
                        btn_text,
                        variant="primary" if index == 0 else "default",
                        name=btn_text,
                        id="modal-dialog-submit-btn" if index == 0 else None
                    )

    @on(Button.Pressed)
    def handle_button(self, event: Button.Pressed):
        # Package the state of all inputs and the button identity
        results = {
            "button_pressed": event.button.name,
            "inputs": {
                ipt.id: ipt.value for ipt in self.query(Input) if ipt.id
            }
        }
        self.dismiss(results)

    @on(Input.Submitted)
    def handle_submit(self):
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
                yield Button("🗑  Remove", id="btn-remove-recent", variant="default")

    @on(Button.Pressed, "#btn-new-project")
    def action_new_project_path(self):
        """Calls the UniversalModal to get a new project path."""

        def handle_modal_result(result: dict | None):
            if not result:
                return

            button = result.get("button_pressed")
            if button != "Create":
                return
            inputs = result.get("inputs", {})
            name = inputs.get("project_name", "").strip()
            path = inputs.get("project_path", "").strip()
            if not path or not name:
                self.notify("Both a name and project path must be provided.", severity="error")
                return
            if not config.path_isdir(path):
                self.notify('Please enter a valid path to a directory.', severity='error')
                return
            self.notify(f"Loaded project at: {path}")
            self.query_one("#recents-list").add_option(Option(f'{name} [grey]({path})[/grey]', name))
            config.RecentProjects.add(name, path)

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
    def on_open(self):
        self.app.push_screen("editor")

    @on(Button.Pressed, "#btn-remove-recent")
    def on_remove(self):
        _: OptionList = cast(OptionList, self.query_one("#recents-list"))
        if (i:=_.highlighted_option) is not None:
            _.remove_option(i.id)
            config.RecentProjects.remove(i.id)
        else:
            self.notify('There is no selection to remove!', severity='warning')


class EditorScreen(Screen):
    """
    The main IDE interface matching Image 2 with dynamic sidebar logic.
    """
    BINDINGS = [
        ("ctrl+s", "save_file", "Save File"),
        ("ctrl+f1", "toggle_left_sidebar", "Toggle Left"),
        ("ctrl+f2", "toggle_right_sidebar", "Toggle Right"),
        ("shift+f1", "toggle_code_editor", "Toggle Code"),
        ("shift+f2", "toggle_bottom_panel", "Toggle Panel"),
        ("ctrl+shift+f1", "toggle_max", "Toggle Max")
    ]

    def compose(self) -> ComposeResult:
        # --- LEFT COLUMN: Project Files ---
        with Vertical(id="project-directory"):
            yield Label("⭘ Project Files", classes="pane-header")
            yield DirectoryTree("./", id="file-tree")
            yield Button("↻  Refresh Directory", classes='full-width gray')
            yield Button("↩  Project Manager", classes='full-width gray')

        # --- MIDDLE COLUMN: Workspace ---
        with Vertical(id="workspace"):
            # Top Toolbar
            with Horizontal(id='workspace-toolbar'):
                yield Label("▼ ", classes='gray')
                yield Select([("Flow 1", str)], id="select-flow", allow_blank=False, compact=True)
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
            yield TextArea.code_editor(
                text="// Select a .flow file to begin...",
                id="code-editor",
                disabled=True
            )

            # Plugin Panel
            with TabbedContent(id="plugin-panel"):
                # TODO: loop through the plugin TabPanes and yield them here
                pass
                # with TabPane("test"):
                #     yield Label("Graph/Network Visualization Placeholder")

        # --- RIGHT COLUMN: Plugin Control Menu ---
        with Vertical(id="plugin-controls"):
            yield Label("⭘ Run Settings", classes="pane-header", id="plugin-controls-header")
            with ContentSwitcher(id="sidebar-switcher"):
                # TODO: loop through the collapsable's that the plugin provides, and place in Vertical containers.
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

    @on(TabbedContent.TabActivated)
    def on_tab_switch(self, event: TabbedContent.TabActivated):
        """
        Dynamically switches the Right Sidebar content AND Title.
        """
        pass  # TODO auto switch the plugin controls...

    @on(Button.Pressed, "#btn-run")
    def action_run(self):
        pass

    @on(Button.Pressed, "#btn-clear")
    def action_clear(self):
        pass


class Main(App):
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
    ]

    def on_mount(self):
        # self.model = Model()  # this is the Model side of the MVC design
        self.install_screen(WelcomeScreen(), name="welcome")
        self.install_screen(EditorScreen(), name="editor")
        self.push_screen("welcome")

    def action_run_sim(self):
        if isinstance(self.screen, EditorScreen):
            self.screen.action_run()

    def action_save_file(self):
        self.notify("File saved successfully.")


if __name__ == "__main__":
    app = Main()
    app.run()
