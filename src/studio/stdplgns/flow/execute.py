"""
This plugin provides basic executing/undoing features, hot-reload, and several other utilities for interactive with flows.
"""
# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Checkbox, Button, ProgressBar, Label, RichLog
from textual.widget import Widget
from textual.containers import ScrollableContainer
from textual.timer import Timer
from textual.worker import Worker
from textual import events

# Standard Imports
from typing import Iterator
import time
import psutil
import os
import sys
from rich.traceback import Traceback as RichTraceback
from studio.model import Plugin
from lang.interpreter import FlowLang
from lang.bootstrapped import wolfram


class LogView(RichLog):
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
    name = 'execute'
    file_types = ['.flow', '.pflow', '.wpflow']

    @property
    def flow(self) -> FlowLang:
        return self.model.data.setdefault('flow', FlowLang())

    def on_initialized(self) -> None:
        # Connect buttons to our execution logic
        self.view.sig_button_pressed.connect(
            self.handle_btn_press
        )
        self.view.sig_checkbox_changed.connect(
            self.handle_checkbox_change
        )

        # Connect flow signals to update progress bar
        self.flow.on_evolved_step.connect(self._handle_progress_updates)
        self.flow.on_regress_step.connect(self._handle_progress_updates)

        # Attributes
        self._process = psutil.Process(os.getpid())
        self._prev_flowlang_src: str = ''  # for diff checking
        self._hot_after_n_changes: int = 0  # for fast reference
        self._worker: Worker | None = None  # for checking and managing the current thread

    def controls(self) -> Iterator[Widget]:  # NOTE: there aren't many settings for the execute tab due to most controls being available through the DSL.
        self.view.code_editor_text_area.language = {'.wpflow': 'rust'}.get(self.model.file_path.suffix, 'python')  # rust is a mostly good syntax highlighter for wl.
        toolbar_btn = (
            pb:=Button("▶", tooltip="Execute", classes="small-btn green", id="toolbar-btn-exec", compact=True),
            sb:=Button("■", tooltip="Stop", classes="small-btn red", id="toolbar-btn-stop", compact=True),
            Button("⤆", tooltip="Regress", classes="small-btn orange", id="toolbar-btn-regress", compact=True),
            Button("⎚", tooltip="Clear", classes="small-btn red", id="toolbar-btn-clear", compact=True)
        )
        sb.display = False
        self.play_button: Button = pb
        self.stop_button: Button = sb
        for btn in toolbar_btn:
            btn.can_focus = False
            self.view.workspace_toolbar.compose_add_child(btn)

        if self.model.file_path.suffix in ('.pflow', '.wpflow'):
            with Collapsible(title='Programmed Flow', collapsed=False):
                self.exec_args = Input(id='exec-args')
                self.exec_args.border_title = 'Args'
                yield self.exec_args
                self.exec_kwargs = Input(id='exec-kwargs')
                self.exec_kwargs.border_title = 'Kwargs'
                yield self.exec_kwargs
                if self.model.file_path.suffix == '.wpflow':
                    yield Button('Terminate Wolfram', id="terminate-wolfram")
        self.regress_steps = Input(type='integer', value='1')
        self.regress_steps.border_title = 'Regression Steps'
        yield self.regress_steps
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

        yield Label()

        self.hot_reload_timer: Timer = self.view.set_interval(
            1, self._handle_hot_reload,
            pause=True  # start paused.
        )

    def panel(self) -> TabPane | None:
        # Progress Bar Widget
        self.progress_bar = ProgressBar(total=100, show_eta=True, id="exec-progress-bar")
        self.progress_container = Collapsible(
            self.progress_bar,
            title="Execution Progress",
            collapsed=False
        )

        # Standard Output Widget
        self.log_view = LogView(id="log-view", highlight=True, markup=True, wrap=True)
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
        btn: str | None = e.button.id
        if btn == 'toolbar-btn-exec':
            self.execute_flow()
        elif btn == 'toolbar-btn-stop':
            self.execute_stop()
        elif btn == 'toolbar-btn-regress':
            self.execute_regress()
        elif btn == 'toolbar-btn-clear':
            try:
                self.flow.clear_evolution()
                self.log_view.write(f'> [bold #FFA500]Clear flow memory[/]')
            except IndexError: self.log_view.write(f'[bold red]Execution error:[/] clear failed')
        elif btn == 'clear-log':
            self.log_view.clear()
            self.log_view.write(f"[bold green] --- Log Cleared --- [/]")
        elif btn == 'terminate-wolfram':
            wolfram.close_all_wl_sessions()
            self.view.notify('Wolfram Session Terminated')

    def handle_checkbox_change(self, e: Checkbox.Changed):
        btn: str | None = e.checkbox.id
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
            self.execute_flow()

    def _handle_progress_updates(self) -> None:
        self.cft(  # we must call from the main thread to be thread-safe according to docs
            self.progress_bar.update,
            progress=self.flow.n_step_progress * 100
        )
        # import time  # to test slowdowns
        # time.sleep(0.5)

    # noinspection unbound-local-variable
    def _execute(self) -> None:
        # note: use self.cft to be thread-safe on textual side (according to docs on Workers)

        # start profiler recording
        if self.mem_profile.value:
            mem_start = self._process.memory_info().rss / 1024 / 1024
            start_time = time.perf_counter()

        # execute the FlowLang
        try:
            if (suffix:=self.model.file_path.suffix) in ('.pflow', '.wpflow'):
                args = eval(self.exec_args.value) if self.exec_args.value else ()
                kwargs = eval(f'(lambda **k: k)({self.exec_kwargs.value})') if self.exec_kwargs.value else {}
                self.flow.interpret(self.view.code_editor_text_area.text, *args, bootstrapped=suffix, **kwargs)
            else:
                self.flow.interpret(self.view.code_editor_text_area.text)
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

        # upon finishing, toggle the stop button back to play button.
        self.cft(self._toggle_play_stop_buttons)

        # show profiler info
        if self.mem_profile.value:
            mem_end = self._process.memory_info().rss / 1024 / 1024
            elapsed_time = time.perf_counter() - start_time
            mem_diff = mem_end - mem_start
            self.cft(
                self.log_view.write,
                f"\n==== [bold blue]Memory Profile Report[/] ====\n"
                f"Time Spent: {elapsed_time:.4f} seconds\n"
                f"Memory Change: {mem_diff:+.2f} MB\n"
                f"Total Studio Memory: {mem_end:.2f} MB\n"
            )

    def execute_flow(self) -> None:
        """Handles the flow execution and updates the UI components."""
        if self._worker and self._worker.is_running:  # this should not happen, but stop just in case.
            self.log_view.write("[bold red]Threading Error:[/] A flow thread is currently running.")
            return
        try:
            self._worker = self.view.run_worker(
                self._execute,
                thread=True
            )
            self._toggle_play_stop_buttons()  # toggle the play button into a stop button.
            self.log_view.write(f'> [bold green]Execute [u]{self.model.file_path.name}[/][/]')
        except Exception as e:  # note: even though _execute handles exceptions, we still want to catch any unforeseen worker related stuff here.
            if self.show_traceback.value:
                self.log_view.write(RichTraceback.from_exception(*sys.exc_info(), word_wrap=True))
            else:
                self.log_view.write(f"[bold red]Threading Error:[/] {str(e)}.")

    def execute_stop(self) -> None:
        """Handles the flow execution and updates the UI components."""
        self.flow.stop_thread()
        self.log_view.write(f'> [bold red]Stop [u]{self.model.file_path.name}[/][/]')

    def _toggle_play_stop_buttons(self):
        self.play_button.display, self.stop_button.display = self.stop_button.display, self.play_button.display

    def execute_regress(self) -> None:
        """Handles the flow regress and updates the UI components."""
        regress_error_message = lambda m: f'[bold red]Regression Error:[/] {str(m)}'
        if self._worker and self._worker.is_running: # this should not happen, but stop just in case.
            self.log_view.write(regress_error_message("A flow thread is currently running"))
            return
        try:
            steps: int = int(self.regress_steps.value)
            def _():
                try:
                    self.flow.regress(steps)
                    self.cft(self.log_view.write, f'> [bold #FFA500]Regress {steps} steps[/]')
                except Exception as e:
                    if self.show_traceback.value:
                        self.cft(self.log_view.write, RichTraceback.from_exception(*sys.exc_info(), word_wrap=True))
                    else:
                        self.cft(self.log_view.write, regress_error_message(str(e)))
            self._worker = self.view.run_worker(
                _,
                thread=True
            )
        except Exception as e:
            if self.show_traceback.value:
                self.log_view.write(RichTraceback.from_exception(*sys.exc_info(), word_wrap=True))
            else:
                self.log_view.write(regress_error_message(str(e)))
