from lark import Lark, Transformer
from core.numlib import str_to_num, INF
from lang import bootstrapped
from lang.builtin_flows import PRESETS, FLOWS
from typing import Any, cast
import re
from pathlib import Path
WORKING_DIR: Path = Path(__file__).parent
def set_working_dir(cd: Path) -> None:
    global WORKING_DIR
    WORKING_DIR = cd.absolute()


# Builtin flows that our parser must have access to for imports/includes
BUILTIN_FLOWS: dict[str, str] = {}
BUILTIN_FLOWS.update(PRESETS)
BUILTIN_FLOWS.update(FLOWS)

# The formal grammar for our DSL
GRAMMAR = r"""
start: (global_flags | block | instruction_sequence | directive | COMMENT)*

// A statement for global flags, appearing alone.
global_flags: flags

// A instruction block: (-flags) ( sequence of instructions... )
block: "(" flags ")" "(" (instruction_sequence | directive)* ")"  // we allow directives here because they could be rule generation top-level directives.

// Rules inside a group block (must end with a semicolon)
instruction_sequence: (instruction ";")+

instruction: [selector*] operator [target*] [flags]

selector: regex_term
        | range_term
        | literal_term
target: literal_term

regex_term: REGEX_LITERAL
range_term: RANGE_LITERAL
literal_term: SIMPLE_LITERAL

operator: OP_REVERSE
        | OP_OVERWRITE
        | OP_DELETE
        | OP_SHIFT_R
        | OP_SHIFT_L
        | OP_SUB
        | OP_INSERT

// Flags
flags: flag+
flag: FLAG_DEF


// Complex Literals
REGEX_LITERAL: /\/[^\/]+\//
STRING_LITERAL: /"[^"]+"/
RANGE_LITERAL: /\[\s*(?:-?\d+|inf|-inf)?\s*(,\s*(?:-?\d+|inf|-inf)?\s*)?\]/   // Matches [1], [1,2], [1,] or [,2]

// Operators (Longer matches first)
OP_REVERSE:   ">><<"
OP_OVERWRITE: "-->"
OP_DELETE:    "><"
OP_SHIFT_R:   ">>"
OP_SHIFT_L:   "<<"
OP_SUB:       "->"
OP_INSERT:    ">"

// Flags
FLAG_DEF: /-[a-zA-Z][a-zA-Z0-9_]*(\[[^\]]*\])?/

// Identifiers & Targets (Simplified to ensure no conflict with flags/operators)
SIMPLE_LITERAL: /[a-zA-Z0-9_.*]+/

// Structural Tokens (can import other similar standards)
%import common.SIGNED_INT
%import common.WS
%import common.NEWLINE
COMMENT: /#[^\n]*/

// Directives (Example: @Universe(ABA) or @Steps(100))
DIRECTIVE_KEY: /[a-zA-Z0-9_.]+/
DIRECTIVE_VALUE: /[^(\);)]+/
directive: "@" DIRECTIVE_KEY "(" [DIRECTIVE_VALUE] ");"

// Ignore Rules
%ignore WS
%ignore NEWLINE
%ignore COMMENT
"""


def macro_directive(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Macro (like importing, but simply dropping the src right into the ast) from a file or preset"""

    value: str | None = BUILTIN_FLOWS.get(path, None)
    if value is None:
        with open(WORKING_DIR / path) as f:
            value = f.read()
    result = (bootstrapped.bootstrapped_py_parse if path.endswith('.pflow') else parse)(value, *args, **kwargs)
    result['type'] = 'macro'  # we create a "macro" object type so that the transformer can resolve/merge it.
    return result


def intercept_top_level_directive(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Top level directives run BEFORE anything is run. They allow imports/includes to happen, part of constructing the actual flow source."""
    name: str = d['key']
    if name == 'macro':
        return [macro_directive(*d['value'])]
    else:  # if there is nothing to intercept just propagate
        return [d]


class FlowLangTransformer(Transformer):
    """
    Transforms the Lark AST for Flow Lang into a structured Python dictionary,
    handling directives, global flags, rule groups (by distributing flags), and individual instructions.
    """

    # helper
    @staticmethod
    def parse_part(part) -> int | float | str | bool | None:
        p: str = part.strip()
        if p == '':
            return None
        elif p.lower() == 'true':
            return True
        elif p.lower() == 'false':
            return False
        try:
            return str_to_num(p)
        except ValueError:
            return p

    def start(self, items):
        """
        The root of the file. Collects all top-level elements into a single list
        of instructions and a dictionary of ruleset flags.
        """
        directives = []
        global_flags = {}
        instructions = []
        for array in items:
            for item in array:
                if item['type'] == 'directive':
                    directives.append((item['key'], item['value']))
                elif item['type'] == 'global_flags':
                    global_flags.update(item['flags'])
                elif item['type'] == 'instruction':
                    instructions.append(item)
                elif item['type'] == 'macro':
                    directives.extend(item['directives'])
                    global_flags.update(item['global_flags'])
                    instructions.extend(item['instructions'])
        return {
            'directives': directives,
            'global_flags': global_flags,  # the flags the set the defaults
            'instructions': instructions
        }

    def directive(self, items):
        if items[1]:  # detect None for directives such as `@Test.me()` with no arguments
            args: tuple = tuple((self.parse_part(p) for p in items[1].value.split(',')))  # parse the args
        else:
            args: tuple = ()
        return intercept_top_level_directive({
            'type': 'directive',
            'key': items[0].value,
            'value': args
        })

    def global_flags(self, items):
        return [{'type': 'global_flags', 'flags': items[0]}]  # we wrap in a list so that the start() visitor can do less work

    def block(self, items):
        flags = items[0]  # temp
        instructions = items[1]
        for instruction in instructions:  # distribute the flags of the block into its constituents
            for k, v in flags.items():
                instruction['flags'].setdefault(k, v)
        return instructions

    def instruction_sequence(self, items):
        return items

    def instruction(self, items):
        out = {
            "type": 'instruction',
            "selector": [],
            "operator": None,
            "target": [],
            "flags": _ if (_:=items[-1]) else {}
        }
        for i in range(len(items) - 1):  # -1 to prevent looping over the flags dict (or None if there are no flags)
            t: str = items[i]['type']
            if t == 'selector':
                out['selector'].append(items[i])
            elif t == 'operator':
                out['operator'] = items[i]
            elif t == 'target':
                out['target'].append(items[i])
        if (op_type:=out['operator']['operator_type']) in ('OP_SHIFT_R', 'OP_SHIFT_L'):  # special case for these rules
            for t in out['target']:
                t: dict  # to make the IDE recognize it
                t['value'] = str_to_num(t['value']) * (-1 if op_type == 'OP_SHIFT_L' else 1)
                t['target_type'] = 'int'
        return out

    def selector(self, items):
        # Unwrap selector child (regex_term, literal_term, etc.)
        items[0]['selector_type'] = items[0]['type']
        items[0]['type'] = 'selector'
        return items[0]

    def target(self, items):
        items[0]['target_type'] = items[0]['type']
        items[0]['type'] = 'target'
        return items[0]

    def operator(self, items):
        # Unwrap operator
        return {
            "type": 'operator',
            "operator_type": items[0].type,
            "symbol": items[0].value
        }

    # --- Terminals to Values (Unchanged) ---
    def regex_term(self, items):
        return {"type": "regex", "value": items[0].value[1:-1]}

    def literal_term(self, items):
        return {"type": "literal", "value": items[0].value}

    def range_term(self, items):
        # Parse [x,y] or [x]
        content = items[0].value[1:-1]  # strip []

        # Helper to convert part to int or None
        def parse_part(part):
            p = part.strip()
            # Lark returns empty strings for missing parts like in [,2]
            return str_to_num(p) if p else None

        parts = content.split(',')
        if len(parts) == 1:
            start = parse_part(parts[0])
            end = start
        else:  # this will be the case: len(parts) == 2
            start = parse_part(parts[0])
            end = parse_part(parts[1])
            if start is None: start = 0
            if end is None: end = INF

        return {"type": "range", "value": (start, end)}

    # --- Flags ---
    def flags(self, items):
        """
        Collects all individual flag dictionaries into a single dictionary
        that can be merged into a rule, group header, or ruleset.
        """
        flag_dict = {}
        for f in items:
            # f is a dictionary like {'flag_name': value} returned by self.flag
            flag_dict.update(f)
        return flag_dict

    def flag(self, items):
        # Parse the raw flag string "-name[args]"
        raw = items[0].value
        # Remove leading "-"
        raw = raw[1:]

        # Default value for boolean/unit flags (e.g., -a, -nt)
        args: bool = True
        name = raw

        if '[' in raw and raw.endswith(']'):
            name_part, args_part = raw.split('[', 1)
            name = name_part
            args_str = args_part[:-1]  # remove trailing "]"
            if args_str:
                arg_parts = args_str.split(',')
                if len(arg_parts) == 1:
                    args: int | float | str = self.parse_part(arg_parts[0])
                else:
                    args: tuple[int | float | str, ...] = tuple(self.parse_part(p) for p in arg_parts)

        return {name: args}


def FlowLangParser(use_transformer: bool = True) -> Lark:
    """Creates the Lark parser object from which .parse(text) can be called."""
    return Lark(
        grammar=GRAMMAR,
        parser='lalr',
        transformer=FlowLangTransformer() if use_transformer else None
    )


def parse(value: str) -> dict[str, Any]:
    """Recursive parsing helper for top-level directives"""
    # noinspection PyTypeChecker
    return FlowLangParser(use_transformer=True).parse(value)



if __name__ == "__main__":
    pass
    # # example (different rules can be added to ensure correct parsing):

    # parser = FlowLangParser(True)
    # # t = parser.parse("""
    # # // Rule 30
    # # @init(AAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAA);
    # # @import(eca_presets);
    # #
    # # // define the rules
    # # @merge(0);
    # # (-pl[inf] -mr[0,inf]) {
    # #     @decode(wns, AB, 30);
    # # }
    # #
    # # // Run n times
    # # @evolve(16);
    # # """)
    # t = parser.parse("""
    # -a[true]
    # (-b) (BA --> _A_; BA --> _A_;)
    #  """)
    # print(type(t))
    # pprint(t)
