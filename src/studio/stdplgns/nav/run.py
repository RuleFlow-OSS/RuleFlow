"""
This plugin provides basic running/undoing features, hot-reload, and several other utilities for interactive with flows.
"""
# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, ProgressBar, Label, RichLog
from textual.widget import Widget
from textual.containers import ScrollableContainer, Horizontal
from textual.timer import Timer
from textual.worker import Worker

# Standard Imports
from typing import Iterator
import time
import psutil
import os
import sys
from rich.traceback import Traceback as RichTraceback
from studio.model import Plugin
from lang.interpreter import FlowLang


class P(Plugin):
    name = 'run'
    file_types = ['.nav']

    def on_initialized(self) -> None:
        # Connect buttons to our execution logic
        self.view.sig_button_pressed.connect(self.handle_btn_press)
        self.view.sig_checkbox_changed.connect(self.handle_checkbox_change)

        # Attributes
        self._process = psutil.Process(os.getpid())
        self._worker: Worker | None = None  # for checking and managing the current thread

    def controls(self) -> Iterator[Widget]:  # NOTE: there aren't many settings for the run tab due to most controls being available through the DSL.
        toolbar_btn = (
            pb:=Button("▶", tooltip="Execute", classes="small-btn green", id="toolbar-btn-run", compact=True),
            sb:=Button("■", tooltip="Stop", classes="small-btn red", id="toolbar-btn-stop", compact=True),
            Button("⤆", tooltip="Regress", classes="small-btn orange", id="toolbar-btn-regress", compact=True),
            Button("⨯", tooltip="Clear", classes="small-btn red", id="toolbar-btn-clear", compact=True)
        )
        sb.display = False
        self.play_button: Button = pb
        self.stop_button: Button = sb
        for btn in toolbar_btn:
            btn.can_focus = False
            self.view.workspace_toolbar.compose_add_child(btn)

        self.regress_steps = Input(type='integer', value='1')
        self.regress_steps.border_title = 'Regression Steps'
        yield self.regress_steps
        with Collapsible(title='Program Log', collapsed=False):
            self.mem_profile = Checkbox('Show memory profile')
            yield self.mem_profile
            self.show_traceback = Checkbox('Show tracebacks')
            yield self.show_traceback
        yield Label()

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
            title="Navigator Log", collapsed=False
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
        if btn == 'toolbar-btn-run':
            self.execute_flow()
        elif btn == 'toolbar-btn-stop':
            self.execute_stop()
        elif btn == 'toolbar-btn-regress':
            self.execute_regress()
        elif btn == 'toolbar-btn-clear':
            pass
        elif btn == 'clear-log':
            self.log_view.clear()
            self.log_view.write(f"[bold green] --- Log Cleared --- [/]")

    def handle_checkbox_change(self, e: Checkbox.Changed):
        pass

    def _execute(self) -> None:
        # use self.cft to be thread-safe on textual side (according to docs on Workers)
        pass

    def execute_flow(self) -> None:
        """Handles the flow execution and updates the UI components."""
        pass

    def execute_stop(self) -> None:
        """Handles the flow execution and updates the UI components."""
        pass

    def _toggle_play_stop_buttons(self):
        self.play_button.display, self.stop_button.display = self.stop_button.display, self.play_button.display

    def execute_regress(self) -> None:
        """Handles the flow regress and updates the UI components."""
        pass
