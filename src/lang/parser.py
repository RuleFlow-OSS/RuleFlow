from lark import Lark, Transformer
from core.numlib import str_to_num, INF
from lang.builtin_flows import PRESETS, FLOWS
from typing import Any, Callable, Sequence
from pathlib import Path
WORKING_DIR: Path = Path(__file__).parent
def set_working_dir(cd: Path) -> None:
    global WORKING_DIR
    WORKING_DIR = cd.absolute()


# The formal grammar for our DSL
GRAMMAR = r"""
// ==========================================
// Top-Level Entry Point
// ==========================================
start: (global_flags | block | instruction_sequence | directive | COMMENT)*

// ==========================================
// High-Level Constructs (Statements)
// ==========================================

// Directives
directive: "@" [/[^;]+/] ";"

// A statement for global flags, appearing alone.
global_flags: flags

// An instruction block: (-flags) ( sequence of instructions... )
block: "(" flags ")" "(" instruction_sequence* ")"

// A sequence of rules (must end with a semicolon)
instruction_sequence: (instruction ";")+



// ==========================================
// Instructions & Expressions
// ==========================================

instruction: selector* operator target* [flags]

selector: regex_term
        | range_term
        | literal_term
        | literal_chars_term
        | fn_term

target: literal_term
      | literal_chars_term
      | fn_term

fn_term: SIMPLE_LITERAL "<" [/[^\>]+/] ">"
literal_term: "(" [/[^)]+/] ")"
literal_chars_term: SIMPLE_LITERAL
regex_term: STRING_LITERAL
range_term: RANGE_LITERAL

operator: OP_OVERWRITE
        | OP_DELETE
        | OP_SUB
        | OP_INSERT

flags: flag+
flag: FLAG_DEF

// ==========================================
// Lexer Terminals (Tokens)
// ==========================================

// Operators (Longer matches defined first)
OP_OVERWRITE: "-->"
OP_DELETE:    "><"
OP_SUB:       "->"
OP_INSERT:    ">"

// Literals & Identifiers
STRING_LITERAL: /"[^"]+"/
RANGE_LITERAL: /\[\s*(?:-?\d+|inf|-inf)?\s*(,\s*(?:-?\d+|inf|-inf)?\s*)?\]/
SIMPLE_LITERAL: /[a-zA-Z0-9_.*]+/

// Flags
FLAG_DEF: /-[a-zA-Z][a-zA-Z0-9_]*(\[[^\]]*\])?/

// Comments
COMMENT: /#[^\n]*/
MULTILINE_COMMENT: /\"\"\"[\s\S]+?\"\"\"/

// ==========================================
// Imports and Ignores
// ==========================================
%import common.SIGNED_INT
%import common.WS
%import common.NEWLINE

// Ignore Rules
%ignore WS
%ignore NEWLINE
%ignore COMMENT
%ignore MULTILINE_COMMENT
"""


def parse_callable_args(s: str) -> tuple[tuple, dict[str, Any]]:
    """parsing helper to support python callable signatures"""
    return eval(f'(lambda *args, **kwargs: (args, kwargs))({s})')


class FlowLangTransformer(Transformer):
    """
    Transforms the Lark AST for Flow Lang into a structured Python dictionary,
    handling directives, global flags, rule groups (by distributing flags), and individual instructions.
    """

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
                    directives.append((item['expr']))
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
        return intercept_top_level_directive({
            'type': 'directive',
            'expr': items[0].value
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
        for i in range(len(items) - 1):  # -1 to prevent looping over the flags
            t: str = items[i]['type']
            if t == 'selector':
                out[t].append(items[i])
            elif t == 'operator':
                out[t] = items[i]
            elif t == 'target':
                out[t].append(items[i])
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
        return {"type": "regex", "value": items[0].value[1:-1].encode()}

    def literal_term(self, items):
        evaluated: Any = eval(items[0].value)
        if isinstance(evaluated, Sequence):
            value: tuple[int, ...] = tuple[int](ord(i) if isinstance(i, str) else i for i in evaluated)
        else:
            value: tuple[int, ...] = (ord(evaluated) if isinstance(evaluated, str) else evaluated,)
        return {
            "type": "literal",
            "value": value
        }

    def literal_chars_term(self, items):
        return {"type": "literal_chars", "value": items[0].value.encode()}

    def range_term(self, items):
        # Parse [x,y] or [x]
        content = items[0].value[1:-1]  # strip "[" and "]"

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

    def fn_term(self, items):
        return {"type": "function", "name": items[0].value, "args": parse_callable_args(items[1].value) if items[1] else None}

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
        raw = items[0].value[1:]

        # Default value for boolean/unit flags (e.g., -a, -nt)
        args: Any = True
        name = raw
        if '[' in raw and raw.endswith(']'):
            name, args_part = raw.split('[', 1)
            args = eval(args_part[:-1], globals={'inf': INF})
        return {name: args}


# Builtin flows that our parser must have access to for imports/includes
BUILTIN_FLOWS: dict[str, str] = {}
BUILTIN_FLOWS.update(PRESETS)
BUILTIN_FLOWS.update(FLOWS)


def macro_directive(path: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Macro (like importing, but simply dropping the src right into the ast) from a file or preset"""
    value: str | None = BUILTIN_FLOWS.get(path, None)
    if value is None:
        with open(WORKING_DIR / path) as f:
            value = f.read()
    result = get_bootstrapped_parse_function(Path(path).suffix)(value, *args, **kwargs)
    result['type'] = 'macro'  # we create a "macro" object type so that the transformer can resolve it.
    return result


def intercept_top_level_directive(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Top level directives run BEFORE anything is run. They allow macros to run, part of constructing the actual flow source."""
    expr: str = d['expr']
    if expr.startswith('macro('):
        return [eval(expr, globals={'macro': macro_directive})]
    else:  # if there is nothing to intercept just propagate
        return [d]


# ==== User Facing ====
def FlowLangParser(use_transformer: bool = True) -> Lark:
    """Creates the Lark parser object from which .parse(text) can be called."""
    return Lark(
        grammar=GRAMMAR,
        parser='lalr',
        transformer=FlowLangTransformer() if use_transformer else None
    )


def parse(value: str, *a, **k) -> dict[str, Any]:
    """Parsing helper for top-level directives.
    Note: any additional args and kwargs are consumed to be compatible with bootstrapped parse functions."""
    return FlowLangParser(use_transformer=True).parse(value)  # type: ignore


def get_bootstrapped_parse_function(suffix: str, default: Any = parse) -> Callable[..., dict[str, Any]] | Any:
    # import bootstrapped parsers here to avoid cyclic import errors
    from lang.bootstrapped.python import bootstrapped_py_parse
    from lang.bootstrapped.wolfram import bootstrapped_wl_parse
    return {
        '.pflow': bootstrapped_py_parse,
        '.wpflow': bootstrapped_wl_parse
    }.get(suffix, default)


if __name__ == "__main__":
    from pprint import pprint
    parser = FlowLangParser(True)
    t = parser.parse(r'''
@macro("stat.ca.preset");
@test(1, "12", (2,2), k=2);
@test2.all()[0].yup(1, 2, 3);
-test[slice(1, 1, 1)]
(-a -j[2])(
    "AAB" AB -> ABA;
    fn<1, 2> -> (1, 2, 3, "A") -ttt;
    [1] --> AB;
    (1, 2, -3, 4) --> AB;
)
(1, 2) ->;
# This is an example of a single line comment!
"""
This is an example of multiline comment.
It is a cool feature!
"""
    ''')

    t = parser.parse(r'''
@macro("stat.eca.pflow", "AB", 30);
    ''')

    t = parser.parse(r'''
# set the initial state
@init("AB");

# define the sequential rules
ABA -> AAB;
A   -> ABA;

# evolve
@evolve(10);
        ''')

    pprint(t)
