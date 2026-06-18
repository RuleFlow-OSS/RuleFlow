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
from studio.stdplgns.sss.enumerator import from_reduced_rank_index

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

        with Collapsible(title='System Exporter', collapsed=False):
            self.export_index = Input(placeholder="Index to Export (e.g. 42)", type="integer")
            yield self.export_index
            self.export_filename = Input(placeholder="filename.flow")
            yield self.export_filename
            yield Button("Export to .flow", id="btn-export", variant="success")

        yield Label()

    def panel(self) -> TabPane | None:
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="run-progress-bar")
        self.progress_container = Collapsible(self.progress_bar, title="Execution Progress", collapsed=False)

        self.results_table = DataTable(id="run-results-table")
        self.results_table.add_columns("Index", "Q-Code", "Rules", "Steps", "Tags/Classification")
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
        elif e.button.id == 'btn-export':
            self.export_flow()

    def _toggle_play_stop_buttons(self):
        self.play_button.display, self.stop_button.display = self.stop_button.display, self.play_button.display

    def export_flow(self) -> None:
        idx_val = self.export_index.value
        if not idx_val:
            self.view.app.notify("Please enter an Index to export.", severity="warning")
            return

        idx = int(idx_val)
        filename = self.export_filename.value.strip() or f"sss_system_{idx}.flow"
        if not filename.endswith('.flow'):
            filename += '.flow'

        try:
            rs_data = from_reduced_rank_index(idx)
            flow_code = f"// Auto-exported SSS System\n"
            flow_code += f"// Index: {rs_data['Index']} | Q-Code: {rs_data['QCode']}\n\n"
            flow_code += '@init("A");\n'

            for match, replace in rs_data["RuleSet"]:
                m_str = match if match else '""'
                r_str = replace if replace else '""'
                flow_code += f"{m_str} -> {r_str};\n"

            with open(filename, 'w') as f:
                f.write(flow_code)
            self.view.app.notify(f"Successfully exported {filename}", title="Export Complete", severity="information")
        except Exception as err:
            self.view.app.notify(f"Failed to export: {err}", title="Export Error", severity="error")

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

        # Wrap the function call so it takes no arguments
        def task():
            self.run_worker_thread(workflow_config)

        # Dispatch it using the App (which is a valid DOMNode)
        self._worker = self.view.app.run_worker(
            task, exclusive=True, thread=True, name="sessie_eval"
        )

    def execute_stop(self) -> None:
        if self._worker: self._worker.cancel()

    def run_worker_thread(self, workflow_config: dict) -> None:
        worker = get_current_worker()

        def ui_progress(pct: float):
            self.view.app.call_from_thread(self.progress_bar.update, progress=pct)

        def ui_log(msg: str):
            self.view.app.call_from_thread(self.log_view.write, msg)

        def ui_result(idx: int, qcode: str, rules: str, steps: int, cls: str):
            self.view.app.call_from_thread(self.results_table.add_row, idx, qcode, rules, steps, cls)

        run_sessie_enumeration(
            workflow_config=workflow_config,
            on_progress=ui_progress,
            on_log=ui_log,
            on_result=ui_result,
            is_cancelled=lambda: worker.is_cancelled
        )

        self.view.app.call_from_thread(self._toggle_play_stop_buttons)
