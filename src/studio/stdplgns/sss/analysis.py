"""
Provides deep analysis metrics for individual SSS Rulesets, with the ability to export
discovered systems to standalone FlowLang (.flow) files.
"""
from textual.widgets import TabPane, Input, Button, Markdown
from textual.containers import VerticalScroll
from textual import work
import os

from studio.model import Plugin
from lang.interpreter import FlowLang
from studio.stdplgns.sss.enumerator import from_reduced_rank_index

class P(Plugin):
    name = 'analysis'
    file_types = ['.sss']

    def on_initialized(self) -> None:
        self.view.sig_button_pressed.connect(self.handle_btn)
        self._current_rs_data = None

    def controls(self):
        self.target_index = Input(placeholder="e.g. 42", type="integer")
        self.target_index.border_title = "Ruleset Index"
        yield self.target_index

        self.steps_input = Input(value="100", type="integer")
        self.steps_input.border_title = "Analysis Steps"
        yield self.steps_input

        self.analyze_btn = Button("Analyze System", id="btn-analyze", variant="primary")
        yield self.analyze_btn

        self.export_filename = Input(value="discovered_system.flow", placeholder="filename.flow")
        self.export_filename.border_title = "Export Path"
        yield self.export_filename

        self.export_btn = Button("Export to .flow", id="btn-export", variant="success", disabled=True)
        yield self.export_btn

    def panel(self) -> TabPane | None:
        self.report_view = Markdown("### Ready for Analysis\nEnter an index and click analyze.")

        return TabPane(
            self.name.title(),
            VerticalScroll(self.report_view, classes="p-4")
        )

    def handle_btn(self, e: Button.Pressed):
        if e.button.id == "btn-analyze":
            idx = int(self.target_index.value or 0)
            steps = int(self.steps_input.value or 100)
            if idx > 0:
                self.export_btn.disabled = True
                self.report_view.update("### Running analysis... Please wait.")
                self.run_analysis(idx, steps)

        elif e.button.id == "btn-export":
            self.export_to_flow()

    def export_to_flow(self) -> None:
        """Compiles the currently analyzed system into FlowLang syntax and saves it."""
        if not self._current_rs_data:
            self.view.app.notify("No system has been analyzed yet.", severity="warning")
            return

        filename = self.export_filename.value.strip() or f"sss_system_{self._current_rs_data['Index']}.flow"
        if not filename.endswith('.flow'):
            filename += '.flow'

        flow_code = f"// Auto-exported SSS System\n"
        flow_code += f"// Index: {self._current_rs_data['Index']} | Q-Code: {self._current_rs_data['QCode']} | Weight: {self._current_rs_data['Weight']}\n\n"
        flow_code += '@init("A");\n'

        for match, replace in self._current_rs_data["RuleSet"]:
            m_str = match if match else '""'
            r_str = replace if replace else '""'
            flow_code += f"{m_str} -> {r_str};\n"

        try:
            with open(filename, 'w') as f:
                f.write(flow_code)
            self.view.app.notify(f"Successfully exported to {os.path.abspath(filename)}", title="Export Complete", severity="information")
        except Exception as err:
            self.view.app.notify(f"Failed to write file: {err}", title="Export Error", severity="error")

    @work(exclusive=True, thread=True)
    def run_analysis(self, index: int, steps: int):
        rs_data = from_reduced_rank_index(index)

        flow_code = '@init("A");\n'
        for match, replace in rs_data["RuleSet"]:
            flow_code += f"{match if match else '\"\"'} -> {replace if replace else '\"\"'};\n"

        flow = FlowLang()
        flow.interpret(flow_code)
        flow.evolve(steps, break_when_inert=True)

        total_events = flow.current_event_idx
        halted = flow.current_event.inert

        space_lengths = []
        for event in flow.events:
            if event.spaces:
                first_space = next(event.spaces, None)
                if first_space:
                    space_lengths.append(len(first_space))

        max_len = max(space_lengths) if space_lengths else 0
        final_len = space_lengths[-1] if space_lengths else 0

        if halted:
            classification = "Class 1: Halts/Inert"
        elif final_len > 10 * steps:
            classification = "Class 3: Rapid/Chaotic Growth"
        elif max_len == final_len and max_len < 50:
            classification = "Class 2: Bounded/Periodic"
        else:
            classification = "Class 4: Complex/Unbounded"

        # Safely inject Markdown backticks without breaking the outer Python code block
        ticks = "```"
        report = f"""
# Analysis Report: Index {index}
**Q-Code:** `{rs_data["QCode"]}`
**Weight:** {rs_data["Weight"]}

### Ruleset
{ticks}flowlang
{flow_code.strip()}
{ticks}

### Simulation Metrics
* **Requested Steps:** {steps}
* **Actual Steps Executed:** {total_events}
* **Halted Early:** {"Yes" if halted else "No"}
* **Maximum String Length:** {max_len} cells
* **Final String Length:** {final_len} cells

### Classification
**Result:** {classification}
        """

        self._current_rs_data = rs_data

        def update_ui():
            self.report_view.update(report)
            self.export_btn.disabled = False

        self.view.app.call_from_thread(update_ui)
