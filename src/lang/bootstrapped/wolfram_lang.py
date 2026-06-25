import re
from typing import Any, Dict, List, Optional
try:
    from wolframclient.evaluation import WolframLanguageSession
    from wolframclient.language import wlexpr
except ImportError:
    raise ImportError('The Wolfram Language and Wolfram Python Client must be installed.')

# same block regex you use
_BLOCK_RE = re.compile(
    r'^([ \t]*)---[ \t]*\n(.*?)^[ \t]*---[ \t]*(?=\n|$)',
    re.MULTILINE | re.DOTALL
)

# split into literal / placeholder parts
_PLACEHOLDER_RE = re.compile(r'\{(.*?)\}', re.DOTALL)

def _escape_wl_literal(s: str) -> str:
    s = s.replace('\\', '\\\\')
    s = s.replace('"', '\\"')
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    s = s.replace('\n', '\\n')
    return s

def _block_to_wl_sow(block_text: str, indent: str = "") -> str:
    """
    Convert a block with {wlExpr} placeholders into a WL Sow[StringJoin[...]] expression.
    Each placeholder becomes ToString[ToExpression["<expr>"], InputForm].
    """
    parts: List[str] = []
    last = 0
    for m in _PLACEHOLDER_RE.finditer(block_text):
        # literal before placeholder
        if m.start() > last:
            lit = block_text[last:m.start()]
            if lit:
                parts.append(f'"{_escape_wl_literal(lit)}"')
        expr = m.group(1).strip()
        # Evaluate expr in WL and convert to string; use InputForm to avoid pretty formatting surprises
        # Wrap ToExpression in Check to return $Failed on syntax/runtime errors
        parts.append(f'ToString[Check[ToExpression["{_escape_wl_literal(expr)}"], $Failed], InputForm]')
        last = m.end()
    # trailing literal
    if last < len(block_text):
        tail = block_text[last:]
        if tail:
            parts.append(f'"{_escape_wl_literal(tail)}"')
    if not parts:
        # empty block -> empty string
        parts = ['""']
    # Build StringJoin of parts and wrap in Sow
    joined = "StringJoin[" + ", ".join(parts) + "]"
    return indent + f"Sow[{joined}];"

def wl_bootstrapped(
    src: str,
    session: WolframLanguageSession,
    *,
    eval_timeout_seconds: Optional[float] = None,
    require_sow_in_blocks: bool = False
) -> List[Any]:
    """
    Process source where WL code is outside --- blocks and flow DSL is inside --- blocks.
    Each --- block may contain WL placeholders { ... } which are evaluated in the WL kernel.
    The function replaces each block with a Sow[...] expression, runs the WL program,
    and returns the collected list of strings.
    If require_sow_in_blocks is True, the block is inserted verbatim (after placeholder
    substitution) and must call Sow[...] itself.
    """
    blocks_replaced = []

    def _repl(m: re.Match) -> str:
        indent = m.group(1) or ""
        block = m.group(2)
        # If caller wants explicit Sow inside blocks, we still perform placeholder substitution
        # but return the substituted text verbatim (caller must Sow)
        if require_sow_in_blocks:
            # substitute placeholders with evaluated expressions at runtime:
            # we convert placeholders into ToString[ToExpression["..."], InputForm] but do NOT wrap in Sow
            # Build a StringJoin expression and return it inline (caller must Sow it)
            parts = []
            last = 0
            for mm in _PLACEHOLDER_RE.finditer(block):
                if mm.start() > last:
                    lit = block[last:mm.start()]
                    if lit:
                        parts.append(f'"{_escape_wl_literal(lit)}"')
                expr = mm.group(1).strip()
                parts.append(f'ToString[Check[ToExpression["{_escape_wl_literal(expr)}"], $Failed], InputForm]')
                last = mm.end()
            if last < len(block):
                tail = block[last:]
                if tail:
                    parts.append(f'"{_escape_wl_literal(tail)}"')
            if not parts:
                return indent + '""'
            return indent + "StringJoin[" + ", ".join(parts) + "];"
        else:
            return _block_to_wl_sow(block, indent)

    wl_source_with_sows = _BLOCK_RE.sub(_repl, src)

    # Wrap in Reap[CompoundExpression[ ... ]][[2,1]] to collect all Sow'd strings
    wrapped = f"Reap[CompoundExpression[{wl_source_with_sows}]][[2,1]]"

    # Evaluate in WL session
    if eval_timeout_seconds is not None:
        result = session.evaluate(wlexpr(wrapped), timeout=eval_timeout_seconds)
    else:
        result = session.evaluate(wlexpr(wrapped))

    return result
