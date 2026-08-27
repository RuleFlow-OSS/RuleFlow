import re
from typing import Any, Optional
from lang.parser import parse

try:
    from wolframclient.evaluation import WolframLanguageSession
    from wolframclient.language import wlexpr, wl
except ImportError:
    raise ImportError('The Wolfram Language and Wolfram Python Client must be installed.')


ACTIVE_SESSIONS: dict[str, WolframLanguageSession] = {}


def open_wl_session(session_name: str = 'default') -> WolframLanguageSession:
    """Gets an active WL session or initializes a new one."""
    if session_name not in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS[session_name] = WolframLanguageSession()
    return ACTIVE_SESSIONS[session_name]


def close_wl_session(session_name: str = 'default') -> WolframLanguageSession:
    """Gets an active WL session or initializes a new one."""
    ACTIVE_SESSIONS[session_name].terminate()
    return ACTIVE_SESSIONS.pop(session_name)


def close_all_wl_sessions() -> None:  # we don't need to make this a callback with `atexit` because active sessions hijack socket protocols are running other threads that prevent natural exiting.
    """Ensures all background Wolfram Kernels are terminated when Python exits.
    This must be called before exiting the main thread."""
    for name, session in ACTIVE_SESSIONS.items():
        session.terminate()


def _escape_wl_literal(s: str) -> str:
    """Escapes string literals for safe injection into Wolfram Language strings."""
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = s.replace('\n', '\\n')
    return s


def bootstrapped_wl_parse(
        src: str,
        *args: Any,
        session_name: str = 'default',
        timeout: Optional[float] = None,
        **kwargs: Any
) -> dict[str, Any]:
    """
    Evaluates Wolfram-bootstrapped FlowLang. Code outside `---` blocks runs as standard WL.
    Code inside `---` blocks is parsed as FlowLang and merged into a final AST.
    Python *args and **kwargs are injected into the WL session namespace.
    """
    pattern = re.compile(r'^([ \t]*)---[ \t]*\n(.*?)^[ \t]*---[ \t]*(?=\n|$)', re.MULTILINE | re.DOTALL)
    placeholder_pattern = re.compile(r'{(.*?)}', re.DOTALL)

    def repl(m: re.Match) -> str:
        indent = m.group(1) or ""
        block = m.group(2)

        parts: list[str] = []
        last = 0

        for mm in placeholder_pattern.finditer(block):
            if mm.start() > last:
                lit = block[last:mm.start()]
                if lit:
                    parts.append(f'"{_escape_wl_literal(lit)}"')
            expr = mm.group(1).strip()

            # --- WL Head Breakdown: The Placeholder Evaluator ---
            # ToExpression: Parses the raw string into executable WL code (e.g., "x + 1" evaluates as math).
            # Check: Acts as a try/except. If ToExpression triggers a WL Message (error), it returns $Failed safely.
            # ToString: Converts the evaluated result back into a string (using OutputForm to strip quotes).
            parts.append(f'ToString[Check[ToExpression["{_escape_wl_literal(expr)}"], $Failed]]')

            last = mm.end()

        if last < len(block):
            tail = block[last:]
            if tail:
                parts.append(f'"{_escape_wl_literal(tail)}"')

        if not parts:
            parts = ['""']

        # --- WL Head Breakdown: String Builder and Output Accumulator ---
        # StringJoin: Concatenates literal FlowLang syntax with the dynamically evaluated placeholder strings.
        # Sow: Emits the constructed string to the background environment to be collected later (like list.append).
        joined = "StringJoin[" + ", ".join(parts) + "]"
        return f"{indent}Sow[{joined}];"

    wl_code = pattern.sub(repl, src)

    # --- Populate session namespace ---
    try:
        session: WolframLanguageSession = open_wl_session(session_name)
    except Exception as e:
        raise RuntimeError(f"Failed to open WL session: {session_name}") from e

    # --- WL Head Breakdown: Namespace Injection ---
    # Set: Translates to `=`. Binds the Python `args` (converted to a WL List) and `kwargs`
    # (converted to a WL Association) to the global WL symbols `args` and `kwargs`.
    session.evaluate(wl.Set(wl.args, args))
    session.evaluate(wl.Set(wl.kwargs, kwargs))

    # --- WL Head Breakdown: Execution Wrapper ---
    # CompoundExpression: Represents the `;` operator. Evaluates the entire generated script sequentially.
    # Reap: Listens for any `Sow` calls during execution and collects them. Returns {result_of_code, {sowed_items}}.
    # [[2]] (Part): Extracts only the second element of Reap's output (the nested list of sowed strings).
    wrapped_wl = f"Reap[CompoundExpression[{wl_code}]][[2]]"

    if timeout is not None:
        result = session.evaluate(wlexpr(wrapped_wl), timeout=timeout)
    else:
        result = session.evaluate(wlexpr(wrapped_wl))

    out: list[str] = []

    def flatten(nested: Any) -> None:
        if isinstance(nested, (list, tuple)):
            for item in nested:
                flatten(item)
        elif isinstance(nested, str):
            out.append(nested)

    flatten(result)

    return parse("".join(out))


if __name__ == "__main__":
    from pprint import pprint
    wl_script = """
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
];
    """
    print("Starting Wolfram Language Session...")
    try:
        ast_1 = bootstrapped_wl_parse(wl_script, "AB", 30)
        print(f"\n--- Parsed AST for ECA Rule v1 ---")
        pprint(ast_1)

        # ast_2 = bootstrapped_wl_parse(wl_script, "AB", 60)
        # print(f"\n--- Parsed AST for ECA Rule v2 ---")
        # pprint(ast_2)
    except Exception as e:
        print(f"\nExecution failed: {e}")
    finally:
        close_all_wl_sessions()
