"""
Implements the code that actually interprets and runs the flows.
"""
from typing import Any, Iterator, Callable
from collections.abc import Sequence
import numpy as np
import importlib.util
from pathlib import Path

# Import the base engine classes
from core.engine import Flow, RuleSet
from core.topologies.nd_space import SpaceState1D, VectorBackendType
from core.topologies.tooling.searcher import VectorRegexSearch, VectorSearch
from lang.parser import parse, get_bootstrapped_parse_function
from lang.implementation import (
    Selector, Target, BaseRule, SubstitutionRule, OverwriteRule, InsertionRule, DeletionRule
)


def import_from_file(file_path: str | Path, *names: str) -> dict[str, Any]:
    """Dynamically imports a specific object or all defined objects from a .py file.

    Args:
        file_path: Path to the .py file.
        names: Optional name of the object to retrieve. If None, returns
          a dictionary of all objects defined in the module.

    Returns:
        The requested object, or a dictionary mapping attribute names to objects.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No file found at: {path}")
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module spec for: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if names:
        objects: dict[str, Any] = {}
        for name in names:
            if not hasattr(module, name):
                raise AttributeError(f"Object '{name}' not found in module '{path.name}'")
            objects[name] = getattr(module, name)
        return objects
    if hasattr(module, "__all__"):  # if __all__ is explicitly defined, prefer that list
        return {
            name: getattr(module, name)
            for name in module.__all__
            if hasattr(module, name)
        }
    return {
        key: value
        for key, value in vars(module).items()
        if not key.startswith("__")
    }



RULE_MAP: dict[str, type[BaseRule]] = {
    "-->": OverwriteRule,
    "><": DeletionRule,
    "->": SubstitutionRule,
    ">": InsertionRule,
}


class Interpreter:
    """An interpreter that translates the transformed AST into working rule flow objects."""
    def __init__(self):
        self.convert_literal_selectors_to_regex_selectors: bool = True
        self.instruction_scope: dict[str, Callable] = {}
        self.directive_scopes: dict[str, dict[str, Any]] = {}  # different sets of directives can be assigned to groups (can be used for different priorities for instance)

    def set_directive_group(self, group_name: str, scope: dict[str, Any]) -> None:
        self.directive_scopes[group_name] = scope

    def set_instruction_scope(self, scope: dict[str, Callable]) -> None:
        self.instruction_scope.update(scope)

    def reset_instruction_scope(self) -> None:
        self.instruction_scope.clear()

    def use_regex_for_literal_selectors(self, b: bool) -> None:
        self.convert_literal_selectors_to_regex_selectors = b

    @staticmethod
    def __convert_dot_wildcard_ord_to_numerical(a: np.ndarray) -> None:
        """
        ord('.') evaluates to 46.
        This finds all elements equal to 46 and replaces them with -1.
        """
        a[a == ord('.')] = -1

    def interpret_selector(self, selector_data: dict[str, Any]) -> Selector:
        """Converts AST selector data into a clean Selector NamedTuple."""
        s_type: str = selector_data["selector_type"]
        s_value = selector_data["value"]

        if s_type == "literal" and self.convert_literal_selectors_to_regex_selectors:
            s_type = "regex"
            s_value: Sequence[int]
            s_value: bytes = bytes(s_value)
        if s_type == "literal_chars":
            s_value: bytes
            if self.convert_literal_selectors_to_regex_selectors:
                s_type = "regex"
            else:
                s_type = "literal"
                s_value: np.ndarray = np.frombuffer(s_value, dtype=np.int8).copy()
                self.__convert_dot_wildcard_ord_to_numerical(s_value)

        if s_type in ("literal", "regex", "range"):
            return Selector(type=s_type, selector=s_value)
        elif s_type == "callable" and s_value in self.instruction_scope:
            s_value: str
            return Selector(type=s_type, selector=self.instruction_scope[s_value])
        raise ValueError(f"Unknown selector of type '{s_type}' with value {s_value}.")

    def interpret_target(self, selector_data: dict[str, Any]) -> Target:
        """Converts AST selector data into a clean Target NamedTuple."""
        t_type: str = selector_data["target_type"]
        t_value = selector_data["value"]
        if t_type in ("literal", "literal_chars"):
            if t_type == "literal_chars":
                t_value: bytes
                t_value: np.ndarray = np.frombuffer(t_value, dtype=np.int8).copy()
                self.__convert_dot_wildcard_ord_to_numerical(t_value)
            else:
                t_value: Sequence[int]
                t_value: np.ndarray = np.asarray(t_value)
            return Target(type="literal", target=t_value)
        elif t_type == "callable" and t_value in self.instruction_scope:
            return Target(type="callable", target=self.instruction_scope[t_value])
        raise ValueError(f"Unknown selector of type '{t_type}' with value {t_value}.")

    def interpret_instructions(self, instructions: Sequence[dict[str, Any]], global_flags: dict[str, Any],
                               regex_searcher: VectorRegexSearch, literal_searcher: VectorSearch) -> Iterator[BaseRule]:
        """
        Iterates over the flat list of instructions, instantiates the correct
        Rule subclass, merges flags, and initializes fields.
        """
        for instruction in instructions:
            operator = instruction['operator']['symbol']
            rule_class = RULE_MAP.get(operator)
            if not rule_class:
                print(f"Warning: Unknown operator '{operator}'. Skipping rule.")
                continue

            # Prepare Selectors and Targets
            if not instruction['selector']:
                print(f'Warning: All rules must have a selector. Skipping rule.')
                continue
            selector = [self.interpret_selector(sd) for sd in instruction['selector']]
            target = [self.interpret_target(td) for td in instruction['target']]

            # Instantiate Rule
            rule_instance: BaseRule = rule_class(selector, target, regex_searcher, literal_searcher)

            # Merge and Assign Flags (Global < Rule/Group)
            final_flags = global_flags.copy()
            rule_flags = instruction.get('flags', {})
            final_flags.update(rule_flags)  # Apply rule/group flags (overwrites global)
            # Apply flags to the rule instance
            for key, value in final_flags.items():
                # Map shorthand keys (e.g., 'pl' for 'parallel_processing_limit') to full attribute names
                setattr(rule_instance, rule_instance.FLAG_ALIAS.get(key, key), value)

            yield rule_instance

    def interpret_directives(self, group_name: str, directives: list[str]) -> list[Any]:
        """
        The directives are just python expressions that must be evaluated.
        """
        scope: dict[str, Any] = self.directive_scopes[group_name]
        evaluated: list[Any] = []
        for expr in directives:
            try:
                evaluated.append(eval(expr, globals=scope))
            except NameError:
                continue
        return evaluated


class FlowLangBase(Flow):
    """The general API of the Flow object used in all language implementations."""

    def interpret_file(self, path: str) -> None:
        """opens `.flow` files and constructs a FlowLang object."""
        with open(path, 'r') as f:
            return self.interpret(f.read())

    def interpret(self, src: str, *args, **kwargs) -> None:
        """Should set the current ruleset and initial space based on interpreted string. Also, handle directives."""
        raise NotImplementedError()


class FlowLang(FlowLangBase):
    """The main interpreter object, it is what actually runs any given code."""
    def __init__(self):
        """Stateful helpers are defined here such as Vector Classes and Interpreters"""
        super().__init__()
        self.ast: dict[str, Any] = {}

        # Vector backend name
        self.vector_backend_type: VectorBackendType = 'vector'

        # Set up the searcher
        self.regex_searcher = VectorRegexSearch()
        self.literal_searcher = VectorSearch()

        # Set up the interpreter
        self.interpreter = Interpreter()

        # NOTE: make sure to update any preset flows (if the below directives are used in them) when names are changed!
        self.interpreter.set_directive_group(
            'initializer',
            {
                'init': self.__init,  # used to set the initial universe conditions.
                'mem': lambda name: setattr(self, 'vector_backend_type', name),  # used to set the memory backend
                'regex_for_literal_selectors': self.interpreter.use_regex_for_literal_selectors,
                'import': lambda path, *names: self.interpreter.set_instruction_scope(
                    import_from_file(path, *names)
                ),  # import names that can be used for selector or target callables
                'reset_imports': self.interpreter.reset_instruction_scope,  # clear all imports
                # 'reset_state': lambda: None,  # TODO: implement a method to reset the settings caused by directive calls.

                # object exposure
                'self': self,
            }
        )
        self.interpreter.set_directive_group(
            'program',
            {
                'evolve': self.evolve,
                'regress': self.regress,
                'clear': self.clear_evolution,
                'merge': self.__merge_group,
                'compress': self.__compress_group,
            }
        )

    def interpret(self, src: str, *args, bootstrapped: str | None = None, **kwargs) -> None:
        self.ast: dict[str, Any] = get_bootstrapped_parse_function(bootstrapped)(src, *args, **kwargs) \
            if bootstrapped else parse(src)

        # interpret initializer directives
        self.interpreter.interpret_directives("initializer", self.ast['directives'])

        # interpret the instructions and convert them to the rule instances
        self._last_instructions_hash: int = 0
        instructions: Sequence[dict[str, Any]] = self.ast['instructions']
        global_flags: dict[str, Any] = self.ast['global_flags']
        instructions_hash: int = hash(str(self.ast['instructions']) + str(self.ast['global_flags']))
        if instructions_hash != self._last_instructions_hash:
            rule_objects: list[BaseRule] = list(
                self.interpreter.interpret_instructions(instructions, global_flags, self.regex_searcher, self.literal_searcher)
            )
            self.set_ruleset(RuleSet(rule_objects))
            self._last_instructions_hash = instructions_hash

        # interpret program-level directives
        self.interpreter.interpret_directives("program", self.ast['directives'])

    def __init(self, *spaces: str | tuple[int | str, ...], as_path: bool = False, **kwargs):
        space_hash: int = hash(spaces)
        # noinspection unresolved-references
        if not self.events or self._last_space_hash != space_hash:  # if events do not exist, it follows that a space hash will not exist and the "or" filters that out in the "if" statement.
            self._last_space_hash = space_hash
            ready_spaces: list[Sequence[int]] = []
            if as_path:
                spaces: tuple[str, ...]
                for space_path in spaces:
                    if space_path.endswith('.npy'):
                        ready_spaces.append(np.load(space_path, **kwargs))
                    else:
                        with open(space_path) as f:
                            ready_spaces.append(np.frombuffer(f.buffer.read(), dtype=np.uint8, **kwargs))
            else:
                for space in spaces:
                    if isinstance(space, str):
                        ready_spaces.append(np.frombuffer(space.encode(), dtype=np.uint8, **kwargs))
                    else:  # if space is tuple
                        ready_spaces.append(tuple[int](ord(c) if isinstance(c, str) else c for c in space))
            # noinspection bad-argument-type
            self.set_initial_space([SpaceState1D(space, self.vector_backend_type) for space in ready_spaces])

    def __merge_group(self, *identifiers: int | str):
        """A directive to merge a particular group into a chain (a composite rule)"""
        rules: list[BaseRule] = self.ruleset.rules  # type: ignore
        for i in range(len(rules)):
            head: BaseRule = rules[i]
            if head.disabled:
                 continue
            if any(i in head.group for i in identifiers):
                for j in range(i + 1, len(rules)):
                    if any(i in rules[j].group for i in identifiers):
                        head.chain.append(rules[j])
                        rules[j].is_in_chain = True
                break

    def __compress_group(self, *identifiers: int | str):
        """A directive to compress a Rule Group such that causality is preserved (no cellular change if the characters look the same)"""
        rules: list[BaseRule] = [rule for rule in self.ruleset.rules  # type: ignore
                                 if any(i in rule.group for i in identifiers) and not rule.disabled]
        for rule in rules:  # If any rule makes no changes, disable it.
            if not isinstance(rule, OverwriteRule):  # we only care about this type of rule... for obvious reasons
                continue
            # we only care about the first selector and target... we can't determine how multiple targets will behave on different match sets.
            selector: Selector = rule.selector[0]
            target: Target = rule.target[0]
            if not (selector.type in ('literal', 'regex') and target.type == 'literal'):
                continue

            rule_is_active: bool = False
            for s, t in zip(selector.selector, target.target):  # type: ignore
                if t == -1:  # -1 is the wildcard-skip quanta
                    continue
                if s != t:
                    rule_is_active = True
                    break
            if not rule_is_active:
                rule.disabled = True


if __name__ == "__main__":
    code = """
# initial state
@init("A" * 15 + "B" + 15 * "A");

# define the rules
@macro("stat.ca.preset");
@macro("stat.eca.pflow", "AB", 30);

# run n times
@clear();
@evolve(14);
        """
    flow = FlowLang()
    flow.interpret(code)
    from pprint import pprint
    for r in flow.ruleset.rules:
        print(r.disabled, r)
    exit()
    pass
    from pprint import pprint
    import psutil
    import os
    import gc
    import timeit

    def get_mem():
        """Returns current resident set size in MB."""
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / 1024 / 1024

    gc.collect()
    mem_start = get_mem()

    # Run Simulation
    code = """
    @init(("A", 66));
    @macro("stat.ca.preset");
    ABA -> (65, 65, "B");
    (65) -> ABA;
    """
    flow = FlowLang()
    flow.interpret(code)

    time = timeit.timeit(lambda: flow.evolve(20), number=1)
    mem_end = get_mem()
    print(f"Total Memory of evolution: {mem_end - mem_start:.2f} MB")
    print(f"Total time spent: {time:.2f} seconds\n")

    # Evolution Table Rendering
    from core.topologies.tooling.prettier import SpaceState1DFormatter
    from rich.console import Console
    formatter = SpaceState1DFormatter()
    formatter.cell_width = 3
    console = Console(width=1000)
    for event in flow.events:
        # noinspection bad-argument-type
        console.print(formatter(next(event.spaces)))
