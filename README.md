# RuleFlow

To see installation details, contribution guidelines, examples, and documentation, please [visit our website](https://www.ruleflow.org/).

RuleFlow is a Python research framework designed to model, evolve, and perform rigorous causal analysis on discrete complex systems.
It was originally developed as a tool for Sequential Substitution Systems for a small research team at Southern Adventist University. It has, of course, evolved and generalized way beyond Sequential Substitution Systems, and we plan to continue our efforts to generalize this projects upper layers (FlowLang and the Studio; the core is already quite general).

Most existing cellular automata and string-rewrite packages in Python treat state transitions as simple transformations of arrays or strings: $S_{t+1} = f(S_t)$. In doing so, they discard the operational lineages, collision dynamics, and spatial causal chains that produced those updates.

RuleFlow tracks complex systems at the level of atomic computational events. It treats updates not as bulk array operations, but as discrete events that destroy and generate spatial quanta. This makes it possible to extract explicit causal DAGs (directed acyclic graphs), measure causal distances to creation events, trace multiway universe branch histories, and study relativistic computational boundaries directly within Python.

The project pairs a high-throughput backend with **FlowLang**—an expressive domain-specific language—and **RuleFlow Studio**, an extensible terminal-based research environment.

---

## What RuleFlow Addresses

1. **A Generalizable Causal Analysis Engine**
RuleFlow tracks spatial changes down to discrete spatial quanta (`Cell` objects with immutable coordinate locations, generations, and unique IDs). When rules fire, state transitions are decomposed into `DeltaCell` units that record exact destroyed and created cells. Every step records an `Event` that preserves its ancestry, allowing downstream extraction of network metrics (e.g., degree assortativity, network density, flow hierarchy, and longest DAG paths) without re-simulating the system.

2. **A Low-Boilerplate, High-Performance DSL (FlowLang)**
Writing rewriting systems and cellular automata by hand often demands tedious array-slicing logic or regex boilerplate. FlowLang introduces a concise syntax for rewrites (`->`), overwrites (`-->`), insertions (`>`), and deletions (`><`). It includes native flags for fine-grained behavioral control, such as parallel execution limits (`-pl`), branch caps (`-bl`), conflict marking protocols (`-cmp`), conflict resolution protocols (`-crp`), and stochastic match thresholds (`-p_rule`, `-p_space`).

3. **Multiway Universe Exploration**
RuleFlow natively supports non-deterministic branching. When multiple rules match or spatial spans conflict, systems can branch off into isolated universe paths. The engine maintains historical spatial links (`parent_delta`), enabling researchers to walk backward through branch histories via coordinate lookups (`(event_idx, space_idx)`).

4. **Bootstrapped Dynamic Scripts**
FlowLang integrates directly with general-purpose programming languages. By enclosing FlowLang statements within `---` blocks, researchers can write standard Python (`.pflow`) or Wolfram Language (`.wpflow`) code to dynamically generate rulesets with loops, mathematical predicates, or automated enumeration logic.

5. **RuleFlow Studio**
A modular, terminal-based GUI built on Textual. Studio offers real-time visualization of evolving spaces, inspection of individual cells via hover events, interactive causal graph generation (via PyVis / VisJS), and an unopinionated plugin architecture for rapid experimentation.


---

## Core Architecture

RuleFlow is structured into modular layers, separating memory management and execution from high-level grammar evaluation:

```text
├── core/                  # Primitives, topologies, and the evolution engine
│   ├── engine.py          # Cell, DeltaCell, Event, Flow, RuleSet, and Rule interfaces
│   ├── signals.py         # Signature-aware event emission system
│   ├── numlib.py          # Arithmetic-compatible Inf and -Inf implementations
│   └── topologies/        # Memory models and vector backends
│       ├── vector.py      # Contiguous numpy-backed vectors and CellVectors
│       └── tooling/       # Boyer-Moore-Horspool, KMP, Rabin-Karp, and regex searchers
├── lang/                  # FlowLang DSL implementation
│   ├── parser.py          # Lark LALR parser grammar and AST transformer
│   ├── interpreter.py     # AST execution and directive handling
│   ├── implementation.py  # Substitution, Overwrite, Insertion, and Deletion rules
│   └── bootstrapped/      # Python and Wolfram execution injectors
├── analysis/              # Causal graphs and terminal formatters
│   ├── causal_graph.py    # NetworkX-backed MultiDiGraph constructor
│   └── prettier.py        # Terminal formatting and cell highlight engines
├── studio/                # RuleFlow Studio (Terminal IDE)
│   ├── model.py           # MVC application state and dynamic plugin loader
│   ├── view.py            # Textual widgets, custom splitters, and session switcher
│   └── stdplgns/          # Built-in plugins (Execute, Explore, Analysis, Sessie Enumeration)
└── tests/                 # Comprehensive test suite (unit, fuzzing, verified snapshots)

```

---

## FlowLang DSL

FlowLang scripts specify the initial state of the universe, configuration directives, and spatial rewrite rules.

### Syntax and Operators

| Operator | Rule Type | Description                                                                                        |
| --- | --- |----------------------------------------------------------------------------------------------------|
| `->` | **Substitution** | Replaces matched selector spans with target values.                                                |
| `-->` | **Overwrite** | Overwrites values at index spans without altering overall vector length (supports `-1` wildcards). |
| `>` | **Insertion** | Inserts target values before the matched selector.                                                 |
| `><` | **Deletion** | Drops matched elements entirely, contracting the universe.                                         |

### Directives & Built-in Functions

* `@init(...)`: Initializes the universe space from a string literal, sequence of integers, or a path to a `.npy` / raw binary file.
* `@evolve(n)`: Evolves the loaded ruleset across $n$ sequential ticks.
* `@regress(n)`: Undoes the specified number of evolution events.
* `@merge(group)`: Merges rules within a group into an atomic composite execution chain.
* `@compress(group)`: Disables rules in a group that produce no effective physical changes to preserve causal cleanliness.
* `@macro("path", ...)`: Directly evaluates and merges an external preset or flow into the AST.


### Rule Flags

Flags modify rule behavior at the global, block, or individual instruction level:

```python
# Global flags: parallel execution limit = infinity, match range = [0, inf]
-pl[inf] -mr[0, inf]

# Grouped block with shared flags: break group on match (-gb), assign to group 1 (-g[1])
(-gb[true] -g[1]) (
    "AAB" -> "BAA";
    "BA"  -> "AB";
)

# Instruction-specific flags: match only in first space, limit rule lifespan to 10 applications
"BB" >< -sr[0, 0] -life[10];
```

* **`-pl[n]`** (`parallel_execution_limit`): Sets how many non-conflicting matches execute within the current branch before spawning an alternate universe.
* **`-bl[n]`** (`branch_limit`): Maximum number of alternate branches the rule can spawn per step.
* **`-cmp["ignore"|"this"|"og"|"both"]`** (`conflict_marking_protocol`): Flags overlapping spatial spans when multiple matches occur.
* **`-crp["branch"|"skip"|"break"|"ignore"]`** (`conflict_resolution_protocol`): Specifies how to handle overlapping rule collisions.
* **`-p_rule[float]` / `-p_space[float]`**: Stochastic probability thresholds for applying a rule or evaluating a space.



---

## Bootstrapped Scripting

When exploring vast combinatorial rule spaces, writing rules by hand becomes impractical. RuleFlow allows embedding dynamic programming blocks directly inside `.pflow` (Python) and `.wpflow` (Wolfram Language) files.

### Python Bootstrapping (`.pflow`)

Python code outside `---` delimiters executes normally, while code inside `---` is parsed as FlowLang. Python variables can be interpolated into the DSL blocks via f-string syntax:

```python
# Generate Elementary Cellular Automata rules dynamically
charset = args[0]
rule_index = args[1]
patterns = [
    (1, 1, 1), (1, 1, 0), (1, 0, 1), (1, 0, 0),
    (0, 1, 1), (0, 1, 0), (0, 0, 1), (0, 0, 0)
]

for (b1, b2, b3), bit in zip(patterns, f'{rule_index:08b}'):
    ---
    {charset[b1]}{charset[b2]}{charset[b3]} --> .{charset[int(bit)]};
    ---
```

### Wolfram Language Bootstrapping (`.wpflow`)

RuleFlow supports Wolfram Language integration for symbolic derivation. Expressions within `{expr}` placeholders inside `---` blocks are evaluated by an active Wolfram kernel session via `wolframclient`:

```mathematica
If[Length[args] < 2, Throw["Missing required arguments"]];
charset = Characters[args[[1]]];
index = args[[2]];
patterns = IntegerDigits[#, 2, 3] & /@ Range[7, 0, -1];
ruleBits = IntegerDigits[index, 2, 8];

Do[
    b1 = charset[[ patterns[[i, 1]] + 1 ]];
    b2 = charset[[ patterns[[i, 2]] + 1 ]];
    b3 = charset[[ patterns[[i, 3]] + 1 ]];
    res = charset[[ ruleBits[[i]] + 1 ]];
    ---
    {b1}{b2}{b3} --> .{res};
    ---
    ,
    {i, 1, 8}
]
```

---

## Causal Graph Analysis

Every state transformation retains the exact indexes of the generations that gave rise to it. Using `EventCausalityGraph`, users can convert live simulations into NetworkX `MultiDiGraph` structures or interactive VisJS visualizations:

```python
from ruleflow.lang import FlowLang
from ruleflow.analysis import EventCausalityGraph
import networkx as nx

flow = FlowLang()
flow.interpret("""
@init("AB");
ABA -> AAB;
A   -> ABA;
@evolve(15);
""")

# Build the directed causal graph across the first 15 events
cg = EventCausalityGraph().build_from_flow(flow, event_range=slice(0, 15))

print(f"Nodes: {cg.number_of_nodes()}")
print(f"Edges: {cg.number_of_edges()}")
print(f"Density: {nx.density(cg):.4f}")
print(f"Longest DAG Path: {nx.dag_longest_path_length(cg)}")
```

Graphs can be exported to standard formats including Gephi (`.gexf`), GraphML (`.graphml`), GML, and Graph6/Sparse6 formats.

---

## RuleFlow Studio

RuleFlow Studio provides a distraction-free terminal IDE built with Textual. It uses an MVC architecture where views bind to decoupled data models via a lightweight signal framework.

### Built-in Capabilities

* **Workspace Variants**: Open temporary, parallel versions of files side-by-side to experiment with parameter changes without altering on-disk sources.
* **Interactive Hover Explorer**: Inspect individual cells directly in the terminal to view their underlying Quanta, Generation, and Identity values. Clicking or toggling highlights shows matching generations or cell IDs across entire evolution runs.
* **Live Execution & Hot Reload**: Step forward, regress, or clear universe histories. Hot reload automatically re-executes simulations after a configured number of editor keystrokes.
* **Graph Inspector**: Render live topological and causal network distributions using terminal sparklines, and trigger interactive browser views via VisJS.
* **System Enumeration**: Filter large combinatorial rule spaces using automated properties (e.g., identity checks, shortening detection, and unbalanced character checks) to isolate chaotic or complex candidates.


### Writing Custom Plugins

Studio is designed to encourage research-oriented tooling rather than imposing rigid, complicated frameworks. Adding a tool requires subclassing `Plugin`, placing the `.py` file into your project's `plugins/` folder, and defining controls and panels:

```python
from typing import Iterator
from textual.widgets import TabPane, Button, RichLog
from textual.widget import Widget
from ruleflow.studio.model import Plugin
from ruleflow.lang import FlowLang


class P(Plugin):
    name = "Metrics Counter"
    file_types = [".flow"]

    @property
    def flow(self) -> FlowLang:
        return self.model.data.setdefault("flow", FlowLang())

    def on_initialized(self) -> None:
        self.view.sig_button_pressed.connect(self._handle_click)

    def controls(self) -> Iterator[Widget]:
        yield Button("Count Cells", id="btn-count")

    def panel(self) -> TabPane:
        self.log = RichLog()
        return TabPane(self.name, self.log)

    def _handle_click(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-count":
            total = sum(len(e.space_deltas) for e in self.flow.events)
            self.log.write(f"Total recorded space deltas: {total}")
```

