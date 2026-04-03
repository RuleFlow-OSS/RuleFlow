# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, ProgressBar, Label, RichLog
from textual.widget import Widget
from textual.containers import ScrollableContainer, Horizontal

# Standard Imports
from typing import Iterator
import time
import psutil
import os
import sys
from rich.traceback import Traceback as RichTraceback
from studio.model import Plugin


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'run'

        # Attributes
        self._process = psutil.Process(os.getpid())

        # Connect the Test button to our execution logic
        self.view.sig_button_pressed.connect(
            self.handle_btn_press
        )

    def controls(self) -> Iterator[Widget]:
        # NOTE: there aren't that many settings for the run tab due to most controls being available through the DSL.

        with Collapsible(title='Hot Reload', collapsed=False):
            self.hot_mode = Checkbox('Enable Hot Reload Mode')
            yield self.hot_mode
            self.hot_n_changes = Input(type='integer', value='1')
            self.hot_n_changes.border_title = 'Re-run after N changes'
            yield self.hot_n_changes
            self.hot_timeout = Input(type='number', value='500')
            self.hot_timeout.border_title = 'Timeout (ms)'
            yield self.hot_timeout

    def panel(self) -> TabPane | None:
        # Progress Bar Widget
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="run-progress-bar")
        self.progress_container = Collapsible(self.progress_bar, title="Execution Progress", collapsed=False)

        # Run Stats Widget (Mem usage & Time)
        self.stats_label = Label("Waiting for run...", id="run-stats-label")
        self.stats_container = Collapsible(self.stats_label, title="Profiler Stats", collapsed=False)

        # Errors & Parser Notes Widget
        self.log_view = RichLog(id="run-log-view", highlight=True, markup=True, wrap=True)
        clear_log = Button('Clear Log', id="clear-log")
        self.show_traceback = Checkbox('Show Traceback')
        self.log_container = Collapsible(
            self.log_view,
            Horizontal(
                clear_log,
                self.show_traceback
            ),
            title="Errors & Parser Notes", collapsed=False)

        return TabPane(
            self.name.title(),
            ScrollableContainer(
                self.progress_container,
                self.stats_container,
                self.log_container
            )
        )

    def handle_btn_press(self, e: Button.Pressed):
        btn: str = e.button.id
        if btn == 'btn-run':
            self.execute_run()
        elif btn == 'clear-log':
            self.clear_log()

    def clear_log(self) -> None:
        self.log_view.clear()
        self.log_view.write(f"[bold green]Cleared Log[/bold green]")

    def execute_run(self) -> None:
        """Handles the flow execution and updates the UI components."""

        active_flow_session = self.model.active_flow
        if not active_flow_session:
            self.log_view.write("[bold red]Studio Error:[/bold red] No active flow selected to run.")
            return

        self.log_view.write(f"[bold green]Executing '{active_flow_session.name}'...[/bold green]")

        # Memory and Time profiling setup
        mem_start = self._process.memory_info().rss / 1024 / 1024
        start_time = time.perf_counter()

        try:
            # Attempt to execute the flow
            self.model.active_flow.flow.interpret(self.view.code_editor_text_area.text)
            self.progress_bar.advance(100)  # Mock completion
        except Exception as e:
            # Handle the exception
            if self.show_traceback.value:
                self.log_view.write(RichTraceback.from_exception(*sys.exc_info()))
            else:
                self.log_view.write(f"[bold red]Execution Error:[/bold red] {str(e)}")

        # Show profiling info to user
        mem_end = self._process.memory_info().rss / 1024 / 1024
        elapsed_time = time.perf_counter() - start_time
        mem_diff = mem_end - mem_start
        self.stats_label.update(
            f"[bold]Time Spent:[/bold] {elapsed_time:.4f} seconds\n"
            f"[bold]Memory Change:[/bold] {mem_diff:+.2f} MB\n"
            f"[bold]Total Memory:[/bold] {mem_end:.2f} MB"
        )
plugin = P()
