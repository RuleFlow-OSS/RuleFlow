from typing import Any
import re
from lang.parser import parse


def bootstrapped_py_parse(src: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """
    Evaluates Python-bootstrapped FlowLang. Code outside `---` blocks runs as standard Python.
    Code inside `---` blocks is parsed as FlowLang and merged into a final AST.
    """
    # Output accumulator for parsed AST fragments
    out: list[str] = []

    # Regex to capture `---` blocks and their preceding indentation.
    # We capture the indent to ensure the generated Python maintains valid scope.
    pattern = re.compile(r'^([ \t]*)---[ \t]*\n(.*?)^[ \t]*---[ \t]*(?=\n|$)', re.MULTILINE | re.DOTALL)
    def repl(m: re.Match) -> str:
        indent = m.group(1)
        content = m.group(2)
        # Escape any triple-quotes inside the DSL snippet to avoid breaking the f-string
        content_escaped = content.replace('"""', r'\"\"\"')
        # Translate the DSL block into an interpolated string execution
        return f"{indent}__out.append(f\"\"\"{content_escaped}\"\"\")"

    # Setup & run execution environment.
    exec_globals = {
        '__out': out,
        'args': args,
        'kwargs': kwargs,
    }
    python_code = pattern.sub(repl, src)
    exec(python_code, exec_globals)
    return parse("".join(out))


if __name__ == "__main__":
    from pprint import pprint
    pprint(bootstrapped_py_parse("""
---
-a[{args[0]}]
---
""", 0))
