# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, ProgressBar, Label, RichLog
from textual.widget import Widget
from textual.containers import ScrollableContainer, Horizontal
from textual.timer import Timer

# Standard Imports
from typing import Iterator
import time
import psutil
import os
import sys
from rich.traceback import Traceback as RichTraceback
from textual.worker import Worker

from studio.model import Plugin, FlowLangBase


class P(Plugin):
    def on_initialized(self) -> None:
        self.name = 'run'

        # Connect buttons to our execution logic
        self.view.sig_button_pressed.connect(
            self.handle_btn_press
        )
        self.view.sig_checkbox_changed.connect(
            self.handle_checkbox_change
        )

        # Connect flow signals to update progress bar
        FlowLangBase.on_evolved_step.connect(self._handle_progress_updates)
        FlowLangBase.on_undone_step.connect(self._handle_progress_updates)

        # Attributes
        self._process = psutil.Process(os.getpid())
        self._prev_flowlang_src: str = ''  # for diff checking
        self._hot_after_n_changes: int = 0  # for fast reference
        self._running_thread: Worker | None = None  # for checking and managing the current thread

    def controls(self) -> Iterator[Widget]:
        # NOTE: there aren't many settings for the run tab due to most controls being available through the DSL.
        with Collapsible(title='Hot Reload', collapsed=False):
            self.hot_mode = Checkbox('Enable hot reload mode', id='hot-reload')
            yield self.hot_mode
            self.hot_after_n_changes = Input(type='integer', value='1', id='hot-after-change')
            self.hot_after_n_changes.border_title = 'After n changes'
            yield self.hot_after_n_changes
        with Collapsible(title='Program Log', collapsed=False):
            self.mem_profile = Checkbox('Show memory profile')
            yield self.mem_profile
            self.show_traceback = Checkbox('Show tracebacks')
            yield self.show_traceback

        self.hot_reload_timer: Timer = self.view.set_interval(
            1, self._handle_hot_reload,
            pause=True  # start paused.
        )

    def panel(self) -> TabPane | None:
        # Progress Bar Widget
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="run-progress-bar")
        self.progress_container = Collapsible(
            self.progress_bar,
            title="Execution Progress",
            collapsed=False
        )

        # Standard Output Widget
        self.log_view = RichLog(id="run-log-view", highlight=True, markup=True, wrap=True)
        self.log_container = Collapsible(
            self.log_view,
            Button('Clear Log', id="clear-log"),
            Label(),
            title="Program Log", collapsed=False
        )

        return TabPane(
            self.name.title(),
            ScrollableContainer(
                self.progress_container,
                self.log_container
            )
        )

    def handle_btn_press(self, e: Button.Pressed):
        btn: str = e.button.id
        if btn == 'btn-run':
            self.execute_run()
        elif btn == 'btn-clear':
            self.model.active_flow.flow.clear_evolution()
        elif btn == 'clear-log':
            self.log_view.clear()
            self.log_view.write(f"[bold green] --- Log Cleared --- [/bold green]")

    def handle_checkbox_change(self, e: Checkbox.Changed):
        btn: str = e.checkbox.id
        if btn == 'hot-reload':
            self.hot_after_n_changes.disabled = e.checkbox.value
            if e.checkbox.value:
                self._hot_after_n_changes = int(self.hot_after_n_changes.value)
                self.hot_reload_timer.resume()
            else:
                self.hot_reload_timer.pause()

    def _flow_src_diff_check(self) -> int:
        a: str = self.view.code_editor_text_area.text
        b: str = self._prev_flowlang_src
        return sum(x != y for x, y in zip(a, b)) + abs(len(a) - len(b))

    def _handle_hot_reload(self) -> None:
        # import time
        # self.log_view.write(time.time())  # for debugging timer
        if self._flow_src_diff_check() >= self._hot_after_n_changes:  # only hot-reload after n changes to src
            self._prev_flowlang_src = self.view.code_editor_text_area.text
            self.execute_run()

    def _handle_progress_updates(self, f: FlowLangBase) -> None:
        self.cft(  # we must call from the main thread to be thread-safe according to docs
            self.progress_bar.update,
            progress=f.n_step_progress * 100
        )
        # import time  # to test slowdowns
        # time.sleep(0.5)

    def _execute(self) -> None:
        # use self.cft to be thread-safe (according to docs on Workers)
        if self.mem_profile.value:
            mem_start = self._process.memory_info().rss / 1024 / 1024
            start_time = time.perf_counter()

        # execute the FlowLang
        try:
            self.model.active_flow.flow.interpret(self.view.code_editor_text_area.text)
        except Exception as e:
            # Handle the exception
            if self.show_traceback.value:
                self.cft(
                    self.log_view.write,
                    RichTraceback.from_exception(*sys.exc_info(), word_wrap=True)
                )
            else:
                self.cft(
                    self.log_view.write,
                    f"[bold red]Execution Error:[/bold red] {str(e)}"
                )

        # show profiler info
        if self.mem_profile.value:
            mem_end = self._process.memory_info().rss / 1024 / 1024
            # noinspection PyUnboundLocalVariable
            elapsed_time = time.perf_counter() - start_time
            # noinspection PyUnboundLocalVariable
            mem_diff = mem_end - mem_start
            self.cft(
                self.log_view.write,
                f"[bold]Time Spent:[/bold] {elapsed_time:.4f} seconds\n"
                f"[bold]Memory Change:[/bold] {mem_diff:+.2f} MB\n"
                f"[bold]Total Studio Memory:[/bold] {mem_end:.2f} MB\n"
            )

    def execute_run(self) -> None:
        """Handles the flow execution and updates the UI components."""
        active_flow = self.model.active_flow
        if not active_flow:
            self.log_view.write("[bold red]Studio Error:[/bold red] No active flow selected to run.")
            return
        if self._running_thread and self._running_thread.is_running:  # do not run while thread is active
            self.log_view.write("[bold red]Studio Error:[/bold red] A flow thread is currently running.")
            return
        self._running_thread = self.view.run_worker(
            self._execute,
            thread=True
        )
        self.log_view.write(f'[bold green]Run "{active_flow.name}" flow...[/bold green]')
        # TODO: maybe more info will be logged at some point (if deemed useful)

plugin = P()
