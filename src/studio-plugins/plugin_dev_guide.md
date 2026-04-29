RuleFlow Studio Plugin Development Guide

1. Architectural Overview

RuleFlow Studio uses a Model-View-Controller (MVC) architecture tightly coupled with a custom reactive signal system. Plugins in RuleFlow Studio act as modular extensions that bridge the Model (engine state) and the View (Textual UI) to provide new functionalities, analysis tools, or visualizers.

Core Components

Model (studio.model.Model): The single source of truth. Manages the workspace, project paths, and the core Cellular Automata/Rule engine (self.flow).

View (studio.view.EditorScreen): The UI controller built on Textual. It manages the layout, consisting of the main workspace (code editor + Plugin Panels) and the right sidebar (Plugin Controls).

Engine (core.engine.Flow): The mathematical simulation engine. It manages the timeline of Event objects, causality graphs, and multi-way branch evaluations.

Signals (core.signals.Signal): A synchronous, QT-like event dispatch system. Used to decouple UI interactions from engine events.

2. The Plugin Interface Contract

Every plugin must inherit from the studio.model.Plugin abstract base class. A plugin is instantiated once per application lifecycle and relies on the Model to inject runtime dependencies before on_initialized is called.

Required Attributes (Injected by Model)

self.name: A string defining the plugin's internal name.

self.model: Access to the Model layer and the simulation engine (self.model.flow).

self.view: Access to the Textual EditorScreen for UI modifications and notifications.

self.cft: A callable (self.view.app.call_from_thread) used to safely update the UI from background worker threads.

Abstract Methods to Implement

on_initialized(self) -> None: Executed after dependencies are injected. Used for state initialization and signal connections.

controls(self) -> Iterator[Widget]: Yields Textual widgets to populate the right-side control sidebar.

panel(self) -> TabPane | None: Returns the primary workspace widget (a TabPane) to be displayed in the center view, or None if the plugin does not require a central visualizer.

3. Step-by-Step Implementation Guide

Step 1: File Structure and Imports

Plugins must be placed in the <project_path>/plugins/ directory. They are dynamically loaded at runtime. Standard Textual widgets and specific engine types should be imported as needed.

from typing import Iterator
from textual.widgets import Collapsible, TabPane, Button, Label, Input
from textual.widget import Widget

from studio.model import Plugin
from core.engine import FlowLangBase


Step 2: Class Definition and Initialization

Create your class inheriting from Plugin. In on_initialized, define local state variables and map UI/Engine signals to internal handlers.

class MyPlugin(Plugin):
    def on_initialized(self) -> None:
        self.name = 'my_plugin'
        
        # Internal state
        self._target_metric: int = 0
        
        # Connect View (UI) Signals
        self.view.sig_button_pressed.connect(self._handle_button_press)
        
        # Connect Engine Signals
        FlowLangBase.on_evolved_n.connect(self._handle_evolution)


Step 3: Building the Sidebar Controls

Implement the controls() method. It is highly recommended to wrap related controls inside a Collapsible widget to maintain sidebar readability. Always assign strict id strings to interactive widgets; these are required for routing signals later.

    def controls(self) -> Iterator[Widget]:
        with Collapsible(title='My Settings', collapsed=False):
            yield Button('Calculate', id='my-calc-btn', variant="primary")
            
            self.metric_input = Input(value='10', id='my-metric-input')
            self.metric_input.border_title = 'Target Metric'
            yield self.metric_input


Step 4: Building the Main Panel

Implement the panel() method. This defines what is rendered in the center workspace. Use Textual containers (VerticalScroll, Horizontal) to manage layout.

    def panel(self) -> TabPane | None:
        self.output_label = Label("Awaiting calculation...")
        
        return TabPane(
            self.name.title(),
            self.output_label
        )


Step 5: Handling Signals

Create the handlers bound in on_initialized.

UI Routing: Use the id of the widget to route logic properly.
Thread Safety: Engine operations (like run.py processing flows) occur in separate workers. If an engine signal triggers a UI update, you must wrap the UI mutation in self.cft().

    def _handle_button_press(self, event: Button.Pressed) -> None:
        if event.button.id == 'my-calc-btn':
            try:
                # Read from UI state
                val = int(self.metric_input.value)
                self.view.notify(f"Calculation started for {val}...")
            except ValueError:
                self.view.notify("Invalid input type.", severity="error")

    def _handle_evolution(self, flow: FlowLangBase, steps: int) -> None:
        # Flow execution happens in a worker thread. 
        # Safely update the Textual UI using self.cft()
        
        def update_ui():
            self.output_label.update(f"Evolved {steps} steps. Total events: {len(flow.events)}")
            
        self.cft(update_ui)


Step 6: Module Export

For the dynamic loader to mount the plugin, a singleton instance of the plugin must be initialized at the bottom of the file.

plugin = MyPlugin()


4. Best Practices & Guidelines

State Management: Do not store complex engine data structures directly on the plugin unless necessary (e.g., caching a graph). Query self.model.flow directly when possible to avoid desync issues.

Idempotent UI Updates: Because Textual's layout phase resolves via generators (yield), do not rely on on_mount lifecycle hooks inside the plugin class. Build the UI statically in controls and panel, caching widget references as instance variables (e.g., self.my_table = DataTable()) to mutate them later.

UI Feedback: Always utilize self.view.notify(message, severity) to give users feedback upon completion or failure of a control action.

Graceful Degradation: Engine states can reset (on_clear). Ensure your plugin listens for reset signals to wipe stale visualization data, preventing IndexError exceptions when referencing destroyed Event arrays.

Signal Memory Leaks: While RuleFlow's custom signal system cleans up somewhat safely, ensure that your plugin does not continuously connect anonymous lambda functions to the engine without disconnecting them, which may degrade performance.
