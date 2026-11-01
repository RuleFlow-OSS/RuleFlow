"""
RuleFlow Studio plugin for MIPS32 assembly compilation, causal evolution,
and pre- / post-hardware state inspection.
"""
import os
import sys
import time
from typing import Iterator, Literal
import psutil

from rich.traceback import Traceback as RichTraceback
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Input,
    Label,
    ProgressBar,
    RichLog,
    TabPane,
)
from textual.worker import Worker

from ruleflow.core.engine import Flow
import ruleflow.implementations.asm.assembler as asm
import ruleflow.implementations.asm.prettier as prettier
from ruleflow.studio.model import Plugin


class P(Plugin):
    name = "execute"
    file_types = [".asm"]

    @property
    def flow(self) -> Flow:
        return self.model.data.setdefault("flow", Flow())

    @property
    def bundle(self) -> asm.MipsProgramBundle | None:
        return self.model.data.get("mips_bundle")

    @bundle.setter
    def bundle(self, value: asm.MipsProgramBundle | None) -> None:
        self.model.data["mips_bundle"] = value

    def on_initialized(self) -> None:
        self.view.sig_button_pressed.connect(self.handle_btn_press)
        self.flow.on_evolved_step.connect(self._handle_progress_updates)

        self._process = psutil.Process(os.getpid())
        self._worker: Worker | None = None

    def controls(self) -> Iterator[Widget]:
        self.view.code_editor_text_area.language = "bash"
        toolbar_btn = (
            pb := Button(
                "▶",
                tooltip="Execute",
                classes="small-btn green",
                id="toolbar-btn-exec",
                compact=True,
                disabled=True,
            ),
            sb := Button(
                "■",
                tooltip="Stop",
                classes="small-btn red",
                id="toolbar-btn-stop",
                compact=True,
            ),
            bb := Button(
                "🛠",
                tooltip="Assemble",
                classes="small-btn green",
                id="toolbar-btn-build",
                compact=True,
            ),
            cb := Button(
                "⎚",
                tooltip="Clear",
                classes="small-btn red",
                id="toolbar-btn-clear",
                compact=True,
            ),
        )
        sb.display = False
        cb.display = False
        self.play_button: Button = pb
        self.stop_button: Button = sb
        self.build_button: Button = bb
        self.clear_button: Button = cb

        for btn in toolbar_btn:
            btn.can_focus = False
            self.view.workspace_toolbar.compose_add_child(btn)

        self.evolve_steps = Input(type="integer", value="1", id="evolve-steps")
        self.evolve_steps.border_title = "Evolve Steps"
        yield self.evolve_steps

        with Collapsible(title="Assembler & Rules", collapsed=False):
            self.steps_per_rule = Input(
                value="1",
                placeholder="int or 'basic_block'",
                id="steps-per-rule",
            )
            self.steps_per_rule.border_title = "Steps per Rule"
            yield self.steps_per_rule

            self.halt_on_inert = Checkbox(
                "Halt on inert", value=True, id="halt-on-inert"
            )
            yield self.halt_on_inert

            self.stop_on_branch = Checkbox(
                "Stop rule on branch", value=False, id="stop-on-branch"
            )
            yield self.stop_on_branch

            self.track_reads_causal = Checkbox(
                "Track reads as causal", value=True, id="track-reads-causal"
            )
            yield self.track_reads_causal

            self.track_pc_cell = Checkbox(
                "Track $pc as cell", value=False, id="track-pc-cell"
            )
            yield self.track_pc_cell

        with Collapsible(title="Program Log", collapsed=False):
            self.log_build_summary = Checkbox(
                "Show assemble summary", value=True, id="log-build-summary"
            )
            yield self.log_build_summary

            self.log_state_before = Checkbox(
                "Show state before evolve", value=True, id="log-state-before"
            )
            yield self.log_state_before

            self.log_causal_trace = Checkbox(
                "Show causal trace table", value=True, id="log-causal-trace"
            )
            yield self.log_causal_trace

            self.log_state_after = Checkbox(
                "Show state after evolve", value=True, id="log-state-after"
            )
            yield self.log_state_after

            self.log_registers = Checkbox(
                "Include registers", value=True, id="log-registers"
            )
            yield self.log_registers

            self.log_memory = Checkbox(
                "Include memory dump", value=True, id="log-memory"
            )
            yield self.log_memory

            self.mem_profile = Checkbox(
                "Show memory profile", value=False, id="log-mem-profile"
            )
            yield self.mem_profile

            self.show_traceback = Checkbox(
                "Show tracebacks", value=False, id="log-show-traceback"
            )
            yield self.show_traceback

        yield Label()

    def panel(self) -> TabPane | None:
        self.progress_bar = ProgressBar(
            total=100, show_eta=True, id="exec-progress-bar"
        )
        self.progress_container = Collapsible(
            self.progress_bar,
            title="Execution Progress",
            collapsed=False,
        )

        self.log_view = RichLog(
            id="log-view",
            highlight=True,
            markup=True,
            wrap=False,
            min_width=145,
        )
        self.log_container = Collapsible(
            self.log_view,
            Button("Clear Log", id="clear-log"),
            Label(),
            title="Program Log",
            collapsed=False,
        )

        return TabPane(
            self.name.title(),
            ScrollableContainer(
                self.progress_container,
                self.log_container,
            ),
        )

    def _set_assembled_state(self, assembled: bool) -> None:
        """Locks/unlocks the editor and updates toolbar buttons based on assembly state."""
        self.build_button.display = not assembled
        self.clear_button.display = assembled
        self.play_button.disabled = not assembled

        self.view.code_editor_text_area.read_only = assembled
        self.view.reload_btn.disabled = assembled

        # Lock assembly-time parameters until cleared
        self.steps_per_rule.disabled = assembled
        self.stop_on_branch.disabled = assembled
        self.track_reads_causal.disabled = assembled
        self.track_pc_cell.disabled = assembled

    def _toggle_play_stop_buttons(self) -> None:
        self.play_button.display, self.stop_button.display = (
            self.stop_button.display,
            self.play_button.display,
        )

    def _parse_steps_per_rule(self) -> int | Literal["basic_block"]:
        raw = (self.steps_per_rule.value or "1").strip().lower()
        return "basic_block" if raw == "basic_block" else max(1, int(raw))

    def _handle_progress_updates(self) -> None:
        self.cft(
            self.progress_bar.update,
            progress=self.flow.n_step_progress * 100,
        )

    def _write_error(self, label: str, exc: Exception, from_thread: bool = True) -> None:
        writer = (
            (lambda msg: self.cft(self.log_view.write, msg))
            if from_thread
            else self.log_view.write
        )
        if self.show_traceback.value:
            writer(RichTraceback.from_exception(*sys.exc_info(), word_wrap=True))
        else:
            writer(f"[bold red]{label}:[/bold red] {exc}")

    def handle_btn_press(self, e: Button.Pressed) -> None:
        btn: str | None = e.button.id
        if btn == "toolbar-btn-build":
            self.assemble_program()
        elif btn == "toolbar-btn-exec":
            self.execute_flow()
        elif btn == "toolbar-btn-stop":
            self.execute_stop()
        elif btn == "toolbar-btn-clear":
            self.clear_flow()
        elif btn == "clear-log":
            self.log_view.clear()
            self.log_view.write("[bold green] --- Log Cleared --- [/]")

    def assemble_program(self) -> None:
        """Assembles the MIPS source, initializes the Flow, and locks the editor."""
        if self._worker and self._worker.is_running:
            self.log_view.write(
                "[bold red]Threading Error:[/] A worker is currently running."
            )
            return

        src = self.view.code_editor_text_area.text
        steps_cfg = self._parse_steps_per_rule()

        try:
            bundle = asm.parse_and_load_mips(
                asm_source=src,
                track_reads_as_causal=self.track_reads_causal.value,
                track_pc_as_cell=self.track_pc_cell.value,
                steps_per_rule=steps_cfg,
                stop_on_branch=self.stop_on_branch.value,
            )
            self.bundle = bundle

            if self.flow.events:
                self.flow.clear_evolution()
            self.flow.set_ruleset(bundle.ruleset)
            self.flow.set_initial_space((bundle.initial_space,))
            if len(self.flow.events) > 1:
                self.flow.events = [self.flow.events[-1]]

            self.progress_bar.update(progress=0)
            self._set_assembled_state(True)
            self.log_view.write(
                f"> [bold cyan]Assembled [u]{self.model.file_path.name}[/][/]"
            )

            if self.log_build_summary.value:
                self.log_view.write(
                    prettier.print_bundle_summary(bundle)
                )
        except Exception as exc:
            self._write_error("Assembly Error", exc, from_thread=False)

    def _execute(self, steps: int) -> None:
        """Background worker that evolves the assembled MIPS flow and logs state."""
        if self.mem_profile.value:
            mem_start = self._process.memory_info().rss / 1024 / 1024
            start_time = time.perf_counter()

        try:
            bundle = self.bundle
            if bundle is None:
                raise RuntimeError("Program must be assembled before evolving.")

            pre_len = len(self.flow.events)
            start_step = max(0, pre_len - 1)
            pre_snapshot = prettier.capture_snapshot(bundle)

            if self.log_state_before.value and (
                self.log_registers.value or self.log_memory.value
            ):
                self.cft(
                    self.log_view.write,
                    prettier.print_full_hardware_state(
                        bundle,
                        include_registers=self.log_registers.value,
                        include_memory=self.log_memory.value,
                        title=f"Before Evolve (Step {start_step})"
                    ),
                )

            self.flow.evolve(
                n_steps=steps,
                halt_on_inert=self.halt_on_inert.value,
            )

            post_len = len(self.flow.events)
            end_step = max(0, post_len - 1)

            if self.log_causal_trace.value:
                trace_slice = (
                    slice(0, post_len)
                    if pre_len <= 1
                    else slice(pre_len, post_len)
                )
                self.cft(
                    self.log_view.write,
                    prettier.print_causal_trace(
                        self.flow,
                        bundle,
                        event_range=trace_slice
                    ),
                )

            if self.log_state_after.value and (
                self.log_registers.value or self.log_memory.value
            ):
                self.cft(
                    self.log_view.write,
                    prettier.print_full_hardware_state(
                        bundle,
                        prev_snapshot=pre_snapshot,
                        include_registers=self.log_registers.value,
                        include_memory=self.log_memory.value,
                        title=f"After Evolve (Step {end_step})"
                    ),
                )

            self.cft(self.progress_bar.update, progress=100)

        except Exception as exc:
            self._write_error("Execution Error", exc, from_thread=True)
        finally:
            self.cft(self._toggle_play_stop_buttons)

        if self.mem_profile.value:
            mem_end = self._process.memory_info().rss / 1024 / 1024
            # noinspection unbound-local-variable
            elapsed_time = time.perf_counter() - start_time
            # noinspection unbound-local-variable
            mem_diff = mem_end - mem_start
            self.cft(
                self.log_view.write,
                f"==== [bold blue]Memory Profile[/] ====  "
                f"Time: {elapsed_time:.4f}s │ ΔMem: {mem_diff:+.2f} MB │ Total: {mem_end:.2f} MB",
            )

    def execute_flow(self) -> None:
        """Evolves the assembled MIPS flow by `Evolve Steps`."""
        if self.bundle is None:
            self.log_view.write(
                "[bold yellow]Notice:[/] Assemble the program (🛠) before executing."
            )
            return
        if self._worker and self._worker.is_running:
            self.log_view.write(
                "[bold red]Threading Error:[/] A flow thread is currently running."
            )
            return

        try:
            steps = max(1, int(self.evolve_steps.value or 1))

            self._toggle_play_stop_buttons()
            self.log_view.write(
                f"> [bold green]Evolve [u]{self.model.file_path.name}[/] (+{steps} steps)[/]"
            )
            self._worker = self.view.run_worker(
                lambda: self._execute(steps),
                thread=True,
            )
        except Exception as exc:
            self._write_error("Execution Error", exc, from_thread=False)

    def execute_stop(self) -> None:
        """Stops an active evolution thread."""
        self.flow.stop_thread()
        self.log_view.write(
            f"> [bold red]Stop [u]{self.model.file_path.name}[/][/]"
        )

    def clear_flow(self) -> None:
        """Clears the assembled bundle and flow evolution, unlocking the code editor."""
        if self._worker and self._worker.is_running:
            self.log_view.write(
                "[bold red]Clear Error:[/] Stop execution before clearing."
            )
            return
        try:
            if self.flow.events:
                self.flow.clear_evolution()
            self.bundle = None
            self.progress_bar.update(progress=0)
            self._set_assembled_state(False)
            self.log_view.write(
                "> [bold #FFA500]Cleared assembly & unlocked editor[/]"
            )
        except Exception as exc:
            self._write_error("Clear Error", exc, from_thread=False)
