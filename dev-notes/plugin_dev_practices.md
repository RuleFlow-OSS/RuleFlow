# Best Plugin Development Practices

When developing custom plugins for RuleFlow Studio, adhering to a consistent structure ensures your tools integrate seamlessly with the application's MVC architecture and UI framework.

### 1. Class Structure and Metadata

* **Inherit from the Base Plugin:** Always inherit from `studio.model.Plugin` and conventionally name your main plugin class `P`.
* **Define Metadata:** Explicitly define the `name` (a string) and `file_types` (a list of supported extensions like `['.flow', '.pflow']`) at the class level.
* **Use Properties for Shared State:** Use `@property` decorators to safely fetch and cache shared model data, such as accessing the `FlowLang` interpreter via `self.model.data.setdefault()`.


### 2. Initialization and Signals

* **Use `on_initialized` for Setup:** Do not overload `__init__`. Instead, use the `on_initialized(self)` method to define internal tools, establish default properties, and connect your event signals.
* **Connect to View Signals:** Bind your plugin's handler methods to the application's global UI signals, such as `self.view.sig_button_pressed.connect(...)`.


### 3. Building the User Interface

* **Yield Sidebar Controls:** The `controls(self)` method must return an `Iterator[Widget]`. Use the `yield` keyword to sequentially build your right-hand sidebar UI.
* **Organize with Collapsibles:** Group related inputs, checkboxes, and buttons inside `Collapsible` containers to keep the sidebar uncluttered.
* **Return a Central Panel:** The `panel(self)` method should construct and return a `TabPane`. This pane will house your plugin's primary workspace widgets (e.g., `DataTable`, `Sparkline`, or `RichLog`).


### 4. Event Handling and User Feedback

* **Centralize Event Dispatching:** Create a single handler method for similar events (e.g., `handle_button_press`) that routes the logic to specific internal methods based on the widget's `id` (e.g., `if e.button.id == 'build-graph':`).
* **Isolate Business Logic:** Keep your UI event handlers clean by offloading the actual data processing (like graph generation or file exporting) into private, isolated methods prefixed with an underscore.
* **Provide Contextual Notifications:** Use `self.view.notify()` to communicate successes or gracefully catch and display `Exception` errors to the user (using `severity="error"` or `"information"`).

> **Developer Tip:** The best way to learn the architecture is by reading the source code! Whenever you are designing a new plugin, look directly at the standard built-in plugins (like `p_analysis.py`, `p_asm.py`, or `p_explore.py`) to get inspiration for styling, layout, and event handling.
