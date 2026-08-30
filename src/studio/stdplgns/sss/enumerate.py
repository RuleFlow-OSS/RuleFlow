"""
This plugin provides Sessie-specific research code and batch enumeration capabilities via declarative YAML configs.
"""
import yaml
import csv
from typing import Iterator

from textual.widgets import Collapsible, TabPane, Input, Button, ProgressBar, Label, RichLog, DataTable, SelectionList, Checkbox
from textual.widgets.selection_list import Selection
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.worker import Worker, get_current_worker
from textual import events

from studio.model import Plugin
from studio.stdplgns.sss._pipeline import run_sessie_enumeration
from studio.stdplgns.sss._ruleset_tests import from_reduced_rank_index
from core.topologies.tooling.rff_encoding import chr_rff

class LogView(RichLog):
    """Intercepts stdout and stderr automatically."""
    def on_mount(self):
        self.begin_capture_print()
        self.can_focus = False

    def on_print(self, e: events.Print):
        txt: str = e.text.rstrip('\n')
        if e.stderr:
            self.write(f'[bold red]> stderr:[/bold red] [red]{txt}[/]')
        else:
            if txt: self.write(txt)

class P(Plugin):
    name = 'enumerate'
    file_types = ['.sss']

    def on_initialized(self) -> None:
        self.view.sig_button_pressed.connect(self.handle_btn_press)
        self.view.sig_selection_list_toggled.connect(self.handle_selection_toggle)

        self.view.sig_input_submit.connect(self.handle_input_submit)
        self.view.sig_checkbox_changed.connect(self.handle_checkbox_change)

        self._worker: Worker | None = None
        self._all_results: list[dict] = []
        self._index_range: slice = slice(None, None)

        # REORDERED: Rules at the bottom. Default values updated.
        self._table_columns = [
            ("Index", "index", True),
            ("Q-Code", "qcode", True),
            ("Steps", "steps", False),
            ("Classification", "classification", False),
            ("Status/Jump Reason", "status", True),
            ("Rules", "rules", False),
        ]

    def controls(self) -> Iterator[Widget]:
        self.view.code_editor_text_area.language = 'yaml'

        # Index range control
        self.index_range = Input(value='', placeholder='e.g. 10: or 3:10', id='index-range')
        self.index_range.border_title = 'Index Range'
        yield self.index_range

        self.play_button = Button("▶", tooltip="Execute", classes="small-btn green", id="toolbar-btn-run", compact=True)
        self.stop_button = Button("■", tooltip="Stop", classes="small-btn red", id="toolbar-btn-stop", compact=True)
        self.stop_button.display = False
        clear_btn = Button("⨯", tooltip="Clear", classes="small-btn red", id="toolbar-btn-clear", compact=True)

        for btn in (self.play_button, self.stop_button, clear_btn):
            btn.can_focus = False
            self.view.workspace_toolbar.compose_add_child(btn)

        with Collapsible(title='Table Display', collapsed=False):
            self.table_controls = SelectionList(
                *(Selection(title, key, default) for title, key, default in self._table_columns),
                id='table-controls'
            )
            self.table_controls.border_title = "Visible Columns"

            self.hide_filtered = Checkbox("Hide Skipped/Filtered Rules", id="hide-filtered", value=True)

            self.filter_class = Input(placeholder="Filter Classification (e.g. Class 4)", id="filter-class")
            self.filter_class.border_title = "Show Only Specific Classes"

            # Call this AFTER initializing the widgets above
            self._rebuild_columns()

            yield self.table_controls
            yield self.hide_filtered
            yield self.filter_class

        with Collapsible(title='System Exporter & Tools', collapsed=False):
            # .flow Export Tools
            self.export_filename = Input(placeholder="auto-generates if blank")
            self.export_filename.border_title = "Export Path / Filename"
            yield self.export_filename

            self.export_index = Input(placeholder="Index to Export (e.g. 42)", type="integer")
            self.export_index.border_title = "Target Index"
            yield self.export_index

            yield Button("Export Index to .flow", id="btn-export-flow", variant="success")

            yield Label("\nData Export")

            # ADDED: Separate index range for CSV
            self.csv_export_range = Input(value='', placeholder='e.g. 10: or 3:10', id='csv-export-range')
            self.csv_export_range.border_title = "CSV Export Index Range"
            yield self.csv_export_range

            # CSV Export Tools
            self.export_csv_filename = Input(placeholder="auto-generates if blank")
            self.export_csv_filename.border_title = "CSV Export Path / Filename"
            yield self.export_csv_filename

            yield Button("Export DataTable to CSV", id="btn-export-csv", variant="primary")

        yield Label()

    def panel(self) -> TabPane | None:
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="run-progress-bar")
        self.progress_container = Collapsible(self.progress_bar, title="Execution Progress", collapsed=False)

        self.results_table = DataTable(id="run-results-table", show_cursor=False, zebra_stripes=True)
        self.results_table.styles.overflow_x = "scroll"
        self.results_table.styles.overflow_y = "scroll"

        self.table_container = Collapsible(self.results_table, title="Discovered Systems", collapsed=False)

        self.log_view = LogView(id="run-log-view", highlight=True, markup=True, wrap=True)
        self.log_container = Collapsible(
            self.log_view, Button('Clear Log', id="clear-log"), title="Navigator Log", collapsed=False
        )

        return TabPane(
            self.name.title(),
            ScrollableContainer(self.progress_container, self.table_container, self.log_container)
        )

    def handle_input_submit(self, e: Input.Submitted):
        _id = e.input.id
        if _id == 'index-range':
            try:
                val = e.value.strip()
                if not val:
                    self._index_range = slice(None, None)
                else:
                    sr = val.split(':')
                    a = int(sr[0]) if sr[0] else None
                    b = int(sr[1]) if len(sr) > 1 and sr[1] else None
                    self._index_range = slice(a, b)
                self._rebuild_rows()
            except ValueError:
                self.view.app.notify('Invalid index range format. Use start:stop', severity='warning')
        elif _id == 'filter-class':
            self._rebuild_rows()

    def handle_checkbox_change(self, e: Checkbox.Changed):
        if e.checkbox.id == 'hide-filtered':
            self._rebuild_rows()

    def handle_btn_press(self, e: Button.Pressed):
        btn = e.button.id
        if btn == 'toolbar-btn-run': self.execute_flow()
        elif btn == 'toolbar-btn-stop': self.execute_stop()
        elif btn == 'toolbar-btn-clear':
            self.results_table.clear()
            self._all_results.clear()
            self.progress_bar.update(progress=0)
        elif btn == 'clear-log': self.log_view.clear()
        elif btn == 'btn-export-flow': self.export_flow()
        elif btn == 'btn-export-csv': self.export_csv()

    def handle_selection_toggle(self, e: SelectionList.SelectionToggled):
        if e.selection_list.id == 'table-controls':
            self._rebuild_columns()

    def _rebuild_columns(self):
        self.results_table.clear(columns=True)
        selected = set(self.table_controls.selected)
        for title, key, _ in self._table_columns:
            if key in selected:
                self.results_table.add_column(title, key=key)
        self._rebuild_rows()

    def _rebuild_rows(self):
        # Safety check in case the framework fires this before panel() is fully mounted
        if not hasattr(self, 'results_table'):
            return

        self.results_table.clear()
        start = self._index_range.start
        stop = self._index_range.stop

        # Safely fall back if the UI components haven't bound to the class yet
        filter_text = self.filter_class.value.strip().lower() if hasattr(self, 'filter_class') else ""
        hide_filt = self.hide_filtered.value if hasattr(self, 'hide_filtered') else True

        for row_data in self._all_results:
            idx = row_data["index"]
            if start is not None and idx < start: continue
            if stop is not None and idx >= stop: continue

            if hide_filt and row_data["status"] == "Filtered": continue
            if filter_text and filter_text not in row_data["classification"].lower(): continue

            visible_data = [row_data[key] for _, key, _ in self._table_columns if key in self.table_controls.selected]
            if visible_data:
                self.results_table.add_row(*visible_data)

    def _toggle_play_stop_buttons(self):
        self.play_button.display, self.stop_button.display = self.stop_button.display, self.play_button.display

    def export_csv(self) -> None:
        if not self.results_table.rows:
            self.view.app.notify("DataTable is empty. Run enumeration first.", severity="warning")
            return

        filename_input = self.export_csv_filename.value.strip()

        if not filename_input:
            filename = "enumeration_results.csv"
        else:
            filename = filename_input

        if not filename.endswith('.csv'):
            filename += '.csv'

        from pathlib import Path
        export_path = Path(filename)
        if not export_path.is_absolute():
            export_path = self.model.project_path.joinpath(filename)

        try:
            with open(export_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([col.label for col in self.results_table.columns.values()])
                for row_key in self.results_table.rows:
                    writer.writerow(self.results_table.get_row(row_key))

            self.view.app.notify(f"Successfully exported at:\n{export_path}", severity="information")
        except Exception as err:
            self.view.app.notify(f"Failed to export CSV: {err}", severity="error")

    def export_flow(self) -> None:
        idx_val = self.export_index.value
        if not idx_val:
            self.view.app.notify("Please enter an Index to export.", severity="warning")
            return

        idx = int(idx_val)
        filename_input = self.export_filename.value.strip()

        if not filename_input:
            filename = f"{self.model.file_path.stem}_system_{idx}.flow"
        else:
            filename = filename_input

        if not filename.endswith('.flow'):
            filename += '.flow'

        from pathlib import Path
        export_path = Path(filename)
        if not export_path.is_absolute():
            export_path = self.model.project_path.joinpath(filename)

        try:
            rs_data = from_reduced_rank_index(idx)
            flow_code = f"// Auto-exported SSS System\n"
            flow_code += f"// Index: {rs_data['Index']} | Q-Code: {rs_data['QCode']}\n\n"
            flow_code += '@init("A");\n'

            for match, replace in rs_data["RuleSet"]:
                m_str = "".join(chr_rff(c) for c in match) if match else ''
                r_str = "".join(chr_rff(c) for c in replace) if replace else ''
                if not m_str and not r_str:
                    continue
                elif not m_str:
                    flow_code += f"> {r_str};\n"
                elif not r_str:
                    flow_code += f"{m_str} >< ;\n"
                else:
                    flow_code += f"{m_str} -> {r_str};\n"

            with open(export_path, 'w') as f:
                f.write(flow_code)

            self.view.app.notify(f"Successfully exported at:\n{export_path}", title="Export Complete",
                                 severity="information")
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
        self._all_results.clear()
        self.log_view.write("[bold blue]Starting Sessie Enumeration...[/]")

        def task():
            self.run_worker_thread(workflow_config)

        self._worker = self.view.app.run_worker(
            task, exclusive=True, thread=True, name="sessie_eval"
        )

    def execute_stop(self) -> None:
        if self._worker: self._worker.cancel()

    def run_worker_thread(self, workflow_config: dict) -> None:
        worker = get_current_worker()

        def ui_progress(pct: float):
            self.cft(self.progress_bar.update, progress=pct)

        def ui_result(idx: int, qcode: str, rules: str, steps: int, cls: str, status: str):
            row_data = {"index": idx, "qcode": qcode, "rules": rules, "steps": steps, "classification": cls, "status": status}
            self._all_results.append(row_data)

            def _update_ui():
                if self.hide_filtered.value and status == "Filtered": return
                filter_text = self.filter_class.value.strip().lower()
                if filter_text and filter_text not in cls.lower(): return

                start = self._index_range.start
                stop = self._index_range.stop
                if start is not None and idx < start: return
                if stop is not None and idx >= stop: return

                visible_data = [row_data[key] for _, key, _ in self._table_columns if key in self.table_controls.selected]
                if visible_data:
                    self.results_table.add_row(*visible_data)

            self.cft(_update_ui)

        run_sessie_enumeration(
            workflow_config=workflow_config,
            on_progress=ui_progress,
            on_result=ui_result,
            is_cancelled=lambda: worker.is_cancelled,
            on_log=self.log_view.write
        )

        self.cft(self._toggle_play_stop_buttons)
