"""
This plugin provides Sessie-specific research code and batch enumeration capabilities.
"""
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, ProgressBar, Label, RichLog, DataTable
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual import work
from textual.worker import Worker, get_current_worker

import yaml
import psutil
import os
from typing import Iterator

from studio.model import Plugin
from studio.stdplgns.sss.pipeline import run_sessie_enumeration


class P(Plugin):
    name = 'run'
    file_types = ['.sss']

    def on_initialized(self) -> None:
        self.view.sig_button_pressed.connect(self.handle_btn_press)
        self._process = psutil.Process(os.getpid())
        self._worker: Worker | None = None

    def controls(self) -> Iterator[Widget]:
        self.view.code_editor_text_area.language = 'yaml'

        self.play_button = Button("▶", tooltip="Execute", classes="small-btn green", id="toolbar-btn-run", compact=True)
        self.stop_button = Button("■", tooltip="Stop", classes="small-btn red", id="toolbar-btn-stop", compact=True)
        self.stop_button.display = False

        clear_btn = Button("⨯", tooltip="Clear", classes="small-btn red", id="toolbar-btn-clear", compact=True)

        for btn in (self.play_button, self.stop_button, clear_btn):
            btn.can_focus = False
            self.view.workspace_toolbar.compose_add_child(btn)

        yield Label()

    def panel(self) -> TabPane | None:
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="run-progress-bar")
        self.progress_container = Collapsible(self.progress_bar, title="Execution Progress", collapsed=False)

        self.results_table = DataTable(id="run-results-table")
        self.results_table.add_columns("Index", "Q-Code", "Rules", "Steps", "Classification")
        self.table_container = Collapsible(self.results_table, title="Discovered Systems", collapsed=False)

        self.log_view = RichLog(id="run-log-view", highlight=True, markup=True, wrap=True)
        self.log_container = Collapsible(
            self.log_view, Button('Clear Log', id="clear-log"), title="Navigator Log", collapsed=False
        )

        return TabPane(
            self.name.title(),
            ScrollableContainer(self.progress_container, self.table_container, self.log_container)
        )

    def handle_btn_press(self, e: Button.Pressed):
        if e.button.id == 'toolbar-btn-run':
            self.execute_flow()
        elif e.button.id == 'toolbar-btn-stop':
            self.execute_stop()
        elif e.button.id == 'clear-log':
            self.log_view.clear()
            self.results_table.clear()

    def _toggle_play_stop_buttons(self):
        self.play_button.display, self.stop_button.display = self.stop_button.display, self.play_button.display

    def execute_flow(self) -> None:
        if self._worker and self._worker.is_running: return
        try:
            workflow_config = yaml.safe_load(self.view.code_editor_text_area.text)
        except Exception as e:
            self.log_view.write(f"[bold red]Failed to parse YAML:[/] {e}")
            return

        self._toggle_play_stop_buttons()
        self.results_table.clear()
        self.log_view.write("[bold blue]Starting Sessie Enumeration...[/]")

        self._worker = self.run_worker_thread(workflow_config)

    def execute_stop(self) -> None:
        if self._worker: self._worker.cancel()

    @work(exclusive=True, thread=True)
    def run_worker_thread(self, workflow_config: dict) -> None:
        """Background thread that executes the pipeline and safely updates UI."""
        worker = get_current_worker()

        # Thread-safe callbacks for the pipeline engine using self.view.app
        def ui_progress(pct: float):
            self.view.app.call_from_thread(self.progress_bar.update, progress=pct)

        def ui_log(msg: str):
            self.view.app.call_from_thread(self.log_view.write, msg)

        def ui_result(idx: int, qcode: str, rules: str, steps: int, cls: str):
            self.view.app.call_from_thread(self.results_table.add_row, idx, qcode, rules, steps, cls)

        # Run the isolated Sessie business logic
        run_sessie_enumeration(
            workflow_config=workflow_config,
            on_progress=ui_progress,
            on_log=ui_log,
            on_result=ui_result,
            is_cancelled=lambda: worker.is_cancelled
        )

        self.view.app.call_from_thread(self._toggle_play_stop_buttons)
