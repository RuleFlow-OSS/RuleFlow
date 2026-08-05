"""
==== FUTURE CONSIDERATIONS ====
- For the 'init' directive, maybe use a save eval such as evalidate rather than the current eval().
"""
from typing import Any, Iterator, Sequence, Callable, cast, Literal
import numpy as np

# Import the base engine classes
from core.engine import Cell, Flow, RuleSet
from core.topologies.nd_space import SpaceState1D
from core.topologies.vector import Vector
from core.topologies.tooling import finder
from lang.parser import parse
from lang.bootstrapped.python import bootstrapped_py_parse
from lang.implementation import (
    Selector, Target, BaseRule, SubstitutionRule, OverwriteRule, InsertionRule, DeletionRule
)
from lang.implementation import SelectorCallable, TargetCallable


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
        self.selector_callables: dict[str, SelectorCallable] = {}
        self.target_callables: dict[str, TargetCallable] = {}
        self.directive_objects: dict[str, dict[str, Any]] = {}  # different sets of directives can be assigned to groups (can be used for different priorities for instance)

    def set_selector_callables(self, callables: dict[str, SelectorCallable]) -> None:
        self.selector_callables.update(callables)

    def set_target_callables(self, callables: dict[str, TargetCallable]) -> None:
        self.target_callables.update(callables)

    def unset_selector_callable(self, callable_name: str) -> SelectorCallable:
        return self.selector_callables.pop(callable_name)

    def unset_target_callable(self, callable_name: str) -> TargetCallable:
        return self.target_callables.pop(callable_name)

    def set_directive_group(self, group_name: str, directive_objects: dict[str, Any]) -> None:
        self.directive_objects[group_name] = directive_objects

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
        elif s_type == "callable" and s_value in self.selector_callables:
            s_value: str
            return Selector(type=s_type, selector=self.selector_callables[s_value])
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
        elif t_type == "callable" and t_value in self.target_callables:
            return Target(type="callable", target=self.target_callables[t_value])
        raise ValueError(f"Unknown selector of type '{t_type}' with value {t_value}.")

    def interpret_instructions(self, instructions: Sequence[dict], global_flags: dict[str, Any]) -> Iterator[BaseRule]:
        """
        Iterates over the flat list of instructions, instantiates the correct
        Rule subclass, merges flags, and initializes fields.
        """
        for instruction in instructions:
            operator = instruction['operator']['symbol']
            RuleClass = RULE_MAP.get(operator)
            if not RuleClass:
                print(f"Warning: Unknown operator '{operator}'. Skipping rule.")
                continue

            # Prepare Selectors and Targets
            if not instruction['selector']:
                print(f'Warning: All rules must have a selector. Skipping rule.')
                continue
            selector = [self.interpret_selector(sd) for sd in instruction['selector']]
            target = [self.interpret_target(td) for td in instruction['target']]

            # Instantiate Rule
            rule_instance: BaseRule = RuleClass(selector, target)

            # Merge and Assign Flags (Global < Rule/Group)
            final_flags = global_flags.copy()
            rule_flags = instruction.get('flags', {})
            final_flags.update(rule_flags)  # Apply rule/group flags (overwrites global)
            # Apply flags to the rule instance
            for key, value in final_flags.items():
                # Map shorthand keys (e.g., 'pl' for 'parallel_processing_limit') to full attribute names
                setattr(rule_instance, rule_instance.FLAG_ALIAS.get(key, key), value)

            yield rule_instance

    def interpret_directives(self, group_name: str, directives: list[tuple[str, Any]]) -> dict[str, Any]:
        """
        Use the directives to modify (call) the `objects`.
        """
        objects: dict[str, Any] = self.directive_objects[group_name]
        results: dict[str, Any] = {}
        for path, args in directives:
            parts = path.split('.')
            root_name = parts[0]
            root_obj = objects.get(root_name)
            if not root_obj:
                continue
            current_obj = root_obj
            try:
                for part in parts[1:]:
                    current_obj = getattr(current_obj, part)
            except AttributeError:
                print(f"Error: Could not traverse '{part}' in path '{path}'.")
                continue
            results[path] = current_obj(*args[0], **args[1])
        return results


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

        # Set up the finder
        self.finder = finder.VectorRegexSearch

        # Set up the interpreter
        self.interpreter = Interpreter()

        # NOTE: make sure to update any presets (if the below directives are used in them) when names are changed!
        self.interpreter.set_directive_group(
            'initializer',
            {
                'init': lambda *args: tuple(map(str, args)),  # used to set the initial universe conditions.
                'mem': lambda mode: mode,  # used to set the vec container for the SpaceState.

                # object exposure
                'Self': self,
                'Interpreter': self.interpreter,
                'Finder': self.finder,

                # custom directives
                'set_finder_core': None,  # to change the finder backend
                'reset_state': None,  # to reset the settings caused by directive calls

                # alias directives
                'target_cache': vec.enable_bytes_cache,
                'pattern_cache': vec.enable_pattern_cache,
                'regex_backend': vec.set_regex_backend,
                'regex_compiler_args': vec.set_regex_compiler_args,
                'regex_find_args': vec.set_regex_find_args,
                'search_buffer': vec.enable_search_buffer
            }
        )
        self.interpreter.set_directive_group(
            'program',
            {
                'evolve': self.evolve,
                'regress': self.regress,
                'clear': self.clear_evolution,
                'merge': self.__merge_group,
                'compress': self.__compress_group
            }
        )

    def interpret(self, src: str, *args, bootstrapped: bool = False, **kwargs) -> None:
        self.ast: dict[str, Any] = bootstrapped_py_parse(src, *args, **kwargs) if bootstrapped else parse(src)
        initializer_directive_responses: dict[str, Any] = self.interpreter.interpret_directives("initializer", self.ast['directives'])
        rule_objects: list[BaseRule] = list(
            self.interpreter.interpret_instructions(
                self.ast['instructions'],
                self.ast['global_flags']
            )
        )
        self.set_ruleset(RuleSet(rule_objects))
        Vec: type[vec.Vec] = getattr(vec, initializer_directive_responses.get('mem', vec.Vec.__name__))  # this is the vector we use (vec.Vec is the default)
        if init:=initializer_directive_responses.get('init', None):
            init = tuple(init)
            if not self.events or self._last_init_space != init:
                self._last_init_space = init
                self.set_initial_space([SpaceState(Vec([Cell(s) for s in string])) for string in init])

        # after instantiations
        self.interpreter.interpret_directives("program", self.ast['directives'])

    def __merge_group(self, *identifiers: int | str):
        """A directive to merge a particular group into a chain (a composite rule)"""
        rules: list[BaseRule] = cast(list[BaseRule], self.ruleset.rules)
        for i in range(len(rules)):
            head = rules[i]
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
        rules: list[BaseRule] = [rule for rule in cast(list[BaseRule], self.ruleset.rules)
                                 if any(i in rule.group for i in identifiers) and not rule.disabled]
        for rule in rules:  # If any rule makes no changes, disable it.
            if isinstance(rule, OverwriteRule):  # we only care about this type of rule... for obvious reasons
                continue
            rule_is_active: bool = False
            for target in rule.target:
                for selector in rule.selector:
                    for s_char, t_char in zip(selector.selector, target.target):  # we only care about the first/primary target... (we can't determine how multiple targets will behave on different match sets)
                        if t_char.quanta == '_':
                            continue
                        if s_char != t_char.quanta:
                            rule_is_active = True
            if not rule_is_active:
                rule.disabled = True

    def regress(self, n_steps: int) -> None:
        super().regress(n_steps)
        for space in self.current_event.spaces:  # we must remember to refresh the search buffer if undoing anything...
            space.cells.refresh_search_buffer()

    def clear_evolution(self) -> None:
        super().clear_evolution()
        for space in self.current_event.spaces:  # we must remember to refresh the search buffer if clearing anything...
            space.cells.refresh_search_buffer()


if __name__ == "__main__":
    # import psutil
    # import os
    # import gc
    # import timeit
    #
    # def get_mem():
    #     """Returns current resident set size in MB."""
    #     process = psutil.Process(os.getpid())
    #     return process.memory_info().rss / 1024 / 1024
    #
    # gc.collect()
    # mem_start = get_mem()
    #
    # # Run Simulation
    # code = """
    # // @mem(TrieVec);
    # @init("AB");
    # ABA -> AAB;
    # A -> ABA;
    #
    # // ==== 4-D network ====
    # // BA -> AB;
    # // BC -> ACB;
    # // A -> ACB;
    # """
    # flow = FlowLang(code)
    # time = timeit.timeit(lambda: flow.evolve(18), number=1)
    #
    # mem_end = get_mem()
    # print(f"Total Memory of evolution: {mem_end - mem_start:.2f} MB")
    # print(f"Total time spent: {time:.2f} seconds")
    # flow.print()
    # pprint([r for r in flow.rule_set.rules])  # print the rule objects

    from pprint import pprint
    code = """
    # @mem(TrieVec);
    @test(1, 2, 3, t=2);
    ABA -> AAB;
    A. -> A.A;

    # ==== 4-D network ====
    # BA -> AB;
    # BC -> ACB;
    # A -> ACB;
    """
    ast: dict[str, Any] = parse(code)
    pprint(ast)

    i = Interpreter()
    rules = tuple(i.interpret_instructions(ast['instructions'], ast['global_flags']))
    pprint(rules)

    i.set_directive_group('inits', {'test': lambda *a, **k: (a, k)})
    directive_results = i.interpret_directives(ast['directives'], 'inits')
    pprint(directive_results)
