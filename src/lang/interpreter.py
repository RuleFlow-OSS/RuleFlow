"""
==== FUTURE CONSIDERATIONS ====
- For the 'init' directive, maybe use a save eval such as evalidate rather than the current eval().
"""
from typing import Any, Type, Iterator, Sequence, Callable, cast
type SpecialSelector = Callable[[Any], str]

# Import the base engine classes
from core.engine import Cell, Flow, RuleSet, SpaceState1D as SpaceState
from core import vec
from lang.parser import FlowLangParser
from lang.implementation import (
    Selector, Target, BaseRule, SubstitutionRule, InsertionRule, OverwriteRule,
    DeletionRule, ShiftingRule, ReverseRule
)


RULE_MAPPER: dict[str, Type[BaseRule]] = {
    "->": SubstitutionRule,
    ">": InsertionRule,
    "-->": OverwriteRule,
    "><": DeletionRule,
    ">>": ShiftingRule,
    "<<": ShiftingRule,
    ">><<": ReverseRule,
}


def interpret_selector(selector_data: dict[str, Any], caller_selector: SpecialSelector | None = None) -> Selector:
    """Converts AST selector data into a clean Selector NamedTuple."""
    s_type = selector_data["selector_type"]
    s_value = selector_data["value"]
    if s_type == "literal":
        return Selector(type=s_type, selector=s_value.replace('_', '.'))  # replace '_' with the regex wildcard '.' because we use regex for matching literals as well.
    elif s_type == "regex":
        return Selector(type=s_type, selector=s_value)
    elif s_type == "range":
        return Selector(type=s_type, selector=s_value)
    elif s_type == "llm_prompt" and caller_selector:
        return Selector(type='regex', selector=caller_selector(s_value))
    raise ValueError(f"Unknown selector type: {s_type}")


def interpret_target(selector_data: dict[str, Any]) -> Target:
    """Converts AST selector data into a clean Target NamedTuple."""
    t_type = selector_data["target_type"]
    t_value = selector_data["value"]
    if t_type == "literal":
        return Target(
            type=t_type,
            target=t_value if isinstance(t_value, int) else tuple(Cell(c) for c in t_value)  # this really needs to be a tuple so that vec.Vec is able to cache it properly (tuple is hashable)
        )
    # add more conditionals if additional types are added to the terminal for target
    raise ValueError(f"Unknown target type: {t_type}")


def interpret_instructions(instructions: Sequence[dict], global_flags: dict[str, Any], caller_selector: SpecialSelector | None = None) -> Iterator[BaseRule]:
    """
    Iterates over the flat list of instructions, instantiates the correct
    Rule subclass, merges flags, and initializes fields.
    """
    for instruction in instructions:
        operator = instruction['operator']['symbol']
        RuleClass = RULE_MAPPER.get(operator)
        if not RuleClass:
            print(f"Warning: Unknown operator '{operator}'. Skipping rule.")
            continue

        # Prepare Selectors and Targets
        if not instruction['selector']:
            print(f'Warning: All rules must have a selector. Skipping rule.')
            continue
        selectors = [interpret_selector(sd, caller_selector) for sd in instruction['selector']]
        target = [interpret_target(td) for td in instruction['target']]

        # Instantiate Rule
        rule_instance: BaseRule = RuleClass(selectors, target)

        # Merge and Assign Flags (Global < Rule/Group)
        # Start with global defaults
        final_flags = global_flags.copy()
        rule_flags = instruction.get('flags', {})
        final_flags.update(rule_flags)  # Apply rule/group flags (overwrites global)
        # Apply flags to the rule instance
        for key, value in final_flags.items():
            # Map shorthand keys (e.g., 'pl' for 'parallel_processing_limit') to full attribute names
            setattr(rule_instance, rule_instance.FLAG_ALIAS.get(key, key), value)

        yield rule_instance


def interpret_directives(objects: dict[str, Any], directives: list[tuple[str, Any]]) -> dict[str, Any]:
    """
    Use the directives to modify (call) the `objects`.
    """
    returns: dict[str, Any] = {}
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
            # noinspection PyUnboundLocalVariable
            print(f"Error: Could not traverse '{part}' in path '{path}'.")
            continue

        # process arguments, call the function, store result
        _args: list = []
        _kwargs: dict = {}
        for arg in args:
            if isinstance(arg, str) and '=' in arg:
                k, v = arg.split('=')
                _kwargs[k] = eval(v)  # yes, I know this is not safe... buts it's very useful.
            else:
                _args.append(arg)
        returns[path] = current_obj(*_args, **_kwargs)
    return returns


class FlowLangBase(Flow):
    """The general API of the Flow object used in all language implementations."""

    def interpret_file(self, path: str) -> None:
        """opens `.flow` files and constructs a FlowLang object."""
        with open(path, 'r') as f:
            return self.interpret(f.read())

    def interpret(self, s: str) -> None:
        """Should set the current ruleset and initial space based on interpreted string. Also, handle directives."""
        raise NotImplementedError()


class FlowLang(FlowLangBase):
    """The main interpreter object, it is what actually runs any given code."""

    def interpret(self, s: str) -> None:
        self.ast: dict[str, Any] = cast(dict[str, Any], cast(object, FlowLangParser().parse(s)))  # a bunch of stupid casting due to the Lark.parse() hinting at Tree[Token] return instead of what the transformer returns.
        r: dict[str, Any] = interpret_directives(
            {
                'init': lambda *args: map(eval, map(str, args)),  # used to set the initial universe conditions.
                # We map str to the args because the parser.py auto-converts number characters (and others) to their actual types... str() converts these back.
                # I know, I know... eval is unsafe. But in this context, I think it's fine because FlowLang is a language built on top of python. Just be careful if using FlowLang on a deployed server for users to use.
                'mem': lambda mode: mode,  # used to set the cells container for the SpaceState.

                # setters (note: make sure to update any presets in the parser if names are changed here)
                'target_cache': vec.enable_bytes_cache,
                'pattern_cache': vec.enable_pattern_cache,
                'regex_backend': vec.set_regex_backend,
                'regex_compiler_args': vec.set_regex_compiler_args,
                'regex_find_args': vec.set_regex_find_args,
                'search_buffer': vec.enable_search_buffer
            },
            self.ast['directives']
        )
        self.set_ruleset(RuleSet(
            list(
                interpret_instructions(
                    self.ast['instructions'],
                    self.ast['global_flags']
                )
            )
        ))
        Vec: type[vec.Vec] = getattr(vec, r.get('mem', vec.Vec.__name__))  # this is the vector we use (vec.Vec is the default)
        if not self.events:
            self.set_initial_space([SpaceState(Vec([Cell(s) for s in string])) for string in r['init']])

        # after instantiation
        interpret_directives({
            'evolve': self.evolve,
            'undo': self.undo,
            'clear': self.clear_evolution,
            'merge': self.__merge_group,
            'compress': self.__compress_group
        }, self.ast['directives'])

    def undo(self, n_steps: int) -> None:
        super().undo(n_steps)
        for space in self.current_event.spaces:  # we must remember to refresh the buffer if undoing anything...
            # noinspection PyUnresolvedReferences
            space.cells.refresh_search_buffer()

    def __merge_group(self, identifier: int | str):
        """A directive to merge a particular group into a chain (a composite rule)"""
        rules: list[BaseRule] = cast(list[BaseRule], self.rule_set.rules)
        for i in range(len(rules)):
            if rules[i].disabled:
                 continue
            if rules[i].group == identifier:
                head = rules[i]
                for j in range(i + 1, len(rules)):
                    if rules[j].group == identifier:
                        head.chain.append(rules[j])
                        rules[j].is_in_chain = True
                break

    def __compress_group(self, identifier: int | str):
        """Compress a Rule Group such that causality is preserved (no cellular change if the characters look the same)"""
        rules: list[BaseRule] = [rule for rule in cast(list[BaseRule], self.rule_set.rules)
                                 if rule.group == identifier and not rule.disabled]
        # If any rule makes no changes, disable it.
        for rule in rules:
            if type(rule) != OverwriteRule:  # we only care about this type of rule... for obvious reasons
                continue
            rule_is_active: bool = False
            for target in rule.target:
                for selector in rule.selectors:
                    for s_char, t_char in zip(selector.selector, target.target):  # we only care about the first/primary target... (we can't determine how multiple targets will behave on different match sets)
                        if t_char.quanta == '_':
                            continue
                        if s_char != t_char.quanta:
                            rule_is_active = True
            if not rule_is_active:
                rule.disabled = True


if __name__ == "__main__":
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
    // @mem(TrieVec);
    @init("AB");
    ABA -> AAB;
    A -> ABA;
    
    // ==== 4-D network ====
    // BA -> AB;
    // BC -> ACB;
    // A -> ACB;
    """
    flow = FlowLang(code)
    time = timeit.timeit(lambda: flow.evolve(18), number=1)

    mem_end = get_mem()
    print(f"Total Memory of evolution: {mem_end - mem_start:.2f} MB")
    print(f"Total time spent: {time:.2f} seconds")
    #
    flow.print()
    # pprint([r for r in flow.rule_set.rules])  # print the rule objects
    # from core.graph import CausalGraph
    # g = CausalGraph(flow)
    # g.render_in_browser()
