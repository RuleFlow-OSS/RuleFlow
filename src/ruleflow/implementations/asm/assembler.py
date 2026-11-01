"""
Modular MARS-style MIPS32 parser, pseudo-instruction expander,
multi-instruction rule packer, and Unicorn loader.
"""
import re
import struct
from dataclasses import dataclass, field
from typing import Literal

from keystone import KS_ARCH_MIPS, KS_MODE_BIG_ENDIAN, KS_MODE_MIPS32, Ks
from unicorn import UC_ARCH_MIPS, UC_MODE_BIG_ENDIAN, UC_MODE_MIPS32, Uc
import unicorn.mips_const as mips
import ruleflow.implementations.asm.model as model


DEFAULT_TEXT_ADDR = 0x00400000
DEFAULT_DATA_ADDR = 0x10010000
DEFAULT_STACK_BASE = 0x7FF00000
DEFAULT_STACK_SIZE = 0x00100000
DEFAULT_STACK_INIT = 0x7FFFEFFC
PAGE_SIZE = 0x1000  # 4096-byte (4KB) virtual memory page granularity


MIPS_REG_MAP: dict[str, int] = {
    "$zero": mips.UC_MIPS_REG_ZERO, "$0": mips.UC_MIPS_REG_ZERO,
    "$at": mips.UC_MIPS_REG_AT,     "$1": mips.UC_MIPS_REG_AT,
    "$v0": mips.UC_MIPS_REG_V0,     "$2": mips.UC_MIPS_REG_V0,
    "$v1": mips.UC_MIPS_REG_V1,     "$3": mips.UC_MIPS_REG_V1,
    "$a0": mips.UC_MIPS_REG_A0,     "$4": mips.UC_MIPS_REG_A0,
    "$a1": mips.UC_MIPS_REG_A1,     "$5": mips.UC_MIPS_REG_A1,
    "$a2": mips.UC_MIPS_REG_A2,     "$6": mips.UC_MIPS_REG_A2,
    "$a3": mips.UC_MIPS_REG_A3,     "$7": mips.UC_MIPS_REG_A3,
    "$t0": mips.UC_MIPS_REG_T0,     "$8": mips.UC_MIPS_REG_T0,
    "$t1": mips.UC_MIPS_REG_T1,     "$9": mips.UC_MIPS_REG_T1,
    "$t2": mips.UC_MIPS_REG_T2,     "$10": mips.UC_MIPS_REG_T2,
    "$t3": mips.UC_MIPS_REG_T3,     "$11": mips.UC_MIPS_REG_T3,
    "$t4": mips.UC_MIPS_REG_T4,     "$12": mips.UC_MIPS_REG_T4,
    "$t5": mips.UC_MIPS_REG_T5,     "$13": mips.UC_MIPS_REG_T5,
    "$t6": mips.UC_MIPS_REG_T6,     "$14": mips.UC_MIPS_REG_T6,
    "$t7": mips.UC_MIPS_REG_T7,     "$15": mips.UC_MIPS_REG_T7,
    "$s0": mips.UC_MIPS_REG_S0,     "$16": mips.UC_MIPS_REG_S0,
    "$s1": mips.UC_MIPS_REG_S1,     "$17": mips.UC_MIPS_REG_S1,
    "$s2": mips.UC_MIPS_REG_S2,     "$18": mips.UC_MIPS_REG_S2,
    "$s3": mips.UC_MIPS_REG_S3,     "$19": mips.UC_MIPS_REG_S3,
    "$s4": mips.UC_MIPS_REG_S4,     "$20": mips.UC_MIPS_REG_S4,
    "$s5": mips.UC_MIPS_REG_S5,     "$21": mips.UC_MIPS_REG_S5,
    "$s6": mips.UC_MIPS_REG_S6,     "$22": mips.UC_MIPS_REG_S6,
    "$s7": mips.UC_MIPS_REG_S7,     "$23": mips.UC_MIPS_REG_S7,
    "$t8": mips.UC_MIPS_REG_T8,     "$24": mips.UC_MIPS_REG_T8,
    "$t9": mips.UC_MIPS_REG_T9,     "$25": mips.UC_MIPS_REG_T9,
    "$k0": mips.UC_MIPS_REG_K0,     "$26": mips.UC_MIPS_REG_K0,
    "$k1": mips.UC_MIPS_REG_K1,     "$27": mips.UC_MIPS_REG_K1,
    "$gp": mips.UC_MIPS_REG_GP,     "$28": mips.UC_MIPS_REG_GP,
    "$sp": mips.UC_MIPS_REG_SP,     "$29": mips.UC_MIPS_REG_SP,
    "$fp": mips.UC_MIPS_REG_FP,     "$30": mips.UC_MIPS_REG_FP,
    "$ra": mips.UC_MIPS_REG_RA,     "$31": mips.UC_MIPS_REG_RA,
    "$pc": mips.UC_MIPS_REG_PC,
    "$hi": mips.UC_MIPS_REG_HI,
    "$lo": mips.UC_MIPS_REG_LO,
}

REG_ID_TO_NAME: dict[int, str] = {
    const: name for name, const in MIPS_REG_MAP.items() if not name[1:].isdigit()
}

BRANCH_MNEMONICS: set[str] = {
    "beq", "bne", "blez", "bgtz", "bltz", "bgez", "j", "jal", "jr", "jalr"
}


@dataclass
class DataSymbol:
    """Metadata for a label defined in the `.data` section."""
    name: str
    address: int
    size: int
    directive: str
    initial_words: list[int] = field(default_factory=list)


@dataclass
class MipsProgramBundle:
    """Container returned by `parse_and_load_mips` holding all initialized objects."""
    ruleset: model.MipsRuleSet
    initial_space: model.MipsSpace
    topology: model.MipsTopology
    mu: Uc
    data_symbols: dict[str, DataSymbol]
    text_labels: dict[str, int]
    text_start: int
    text_end: int
    data_start: int
    data_end: int


@dataclass
class _ParsedSections:
    """Internal container holding raw `.data` and `.text` lines and base addresses."""
    data_lines: list[str]
    text_lines: list[str]
    text_base: int
    data_base: int


def to_signed_32(val: int) -> int:
    """Converts an unsigned 32-bit integer into a signed Python int."""
    return val - 0x100000000 if (val & 0x80000000) else val


def _parse_int(token: str) -> int:
    """Parses a decimal, hex, binary, or character literal into an integer."""
    tok = token.strip()
    if tok.startswith("'") and tok.endswith("'") and len(tok) >= 3:
        return ord(eval(tok))
    return int(tok, 0)


def _strip_comments(raw_line: str) -> str:
    """Removes `#` and `;` comments while preserving string literals."""
    in_quotes = False
    quote_char = ""
    for i, ch in enumerate(raw_line):
        if ch in ('"', "'") and (i == 0 or raw_line[i - 1] != "\\"):
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif ch == quote_char:
                in_quotes = False
        elif not in_quotes and ch in ("#", ";"):
            return raw_line[:i].strip()
    return raw_line.strip()


def _extract_labels(line: str) -> tuple[list[str], str]:
    """Extracts any leading `label:` declarations from an assembly line."""
    labels: list[str] = []
    while ":" in line:
        lbl, rest = line.split(":", 1)
        if '"' in lbl or "'" in lbl:
            break
        labels.append(lbl.strip())
        line = rest.strip()
    return labels, line


def _tokenize_instruction(asm_code: str) -> tuple[str, list[str]]:
    """Splits an instruction line into `(mnemonic, operands)`."""
    clean = _strip_comments(asm_code)
    if not clean:
        return "nop", []
    parts = [p.strip() for p in re.split(r"[\s,]+", clean) if p.strip()]
    return parts[0].lower(), parts[1:]


def extract_read_registers(asm_code: str) -> set[int]:
    """Identifies which registers are read as source operands by `asm_code`."""
    mnemonic, ops = _tokenize_instruction(asm_code)
    if not ops and mnemonic not in ("mfhi", "mflo"):
        return set()

    read_regs: set[int] = set()

    def _add_reg(token: str) -> None:
        m = re.search(r"\((\$[a-z0-9]+)\)", token.lower())
        reg_tok = m.group(1) if m else token.lower()
        reg_id = MIPS_REG_MAP.get(reg_tok)
        if reg_id is not None and reg_id != mips.UC_MIPS_REG_ZERO:
            read_regs.add(reg_id)

    if mnemonic in ("sw", "sh", "sb"):
        for op in ops:
            _add_reg(op)
    elif mnemonic in ("lw", "lh", "lhu", "lb", "lbu"):
        if len(ops) >= 2:
            _add_reg(ops[1])
    elif mnemonic in ("beq", "bne", "mult", "multu", "div", "divu"):
        for op in ops[:2]:
            _add_reg(op)
    elif mnemonic in ("blez", "bgtz", "bltz", "bgez", "jr", "mtlo", "mthi"):
        if ops:
            _add_reg(ops[0])
    elif mnemonic == "jalr":
        if ops:
            _add_reg(ops[-1])
    elif mnemonic == "mfhi":
        read_regs.add(mips.UC_MIPS_REG_HI)
    elif mnemonic == "mflo":
        read_regs.add(mips.UC_MIPS_REG_LO)
    elif mnemonic not in ("lui", "j", "jal", "nop"):
        for op in ops[1:]:
            _add_reg(op)

    return read_regs


def extract_write_registers(asm_code: str) -> set[int]:
    """Identifies which registers are written as destinations by `asm_code`."""
    mnemonic, ops = _tokenize_instruction(asm_code)
    write_regs: set[int] = set()

    def _add_reg(token: str) -> None:
        reg_id = MIPS_REG_MAP.get(token.lower())
        if reg_id is not None and reg_id != mips.UC_MIPS_REG_ZERO:
            write_regs.add(reg_id)

    if mnemonic in (
        "sw", "sh", "sb", "beq", "bne", "blez", "bgtz", "bltz", "bgez", "j", "jr", "nop"
    ):
        return write_regs
    if mnemonic == "jal":
        write_regs.add(mips.UC_MIPS_REG_RA)
    elif mnemonic == "jalr":
        if len(ops) == 1:
            write_regs.add(mips.UC_MIPS_REG_RA)
        elif len(ops) >= 2:
            _add_reg(ops[0])
    elif mnemonic in ("mult", "multu", "div", "divu"):
        write_regs.update({mips.UC_MIPS_REG_HI, mips.UC_MIPS_REG_LO})
    elif mnemonic == "mthi":
        write_regs.add(mips.UC_MIPS_REG_HI)
    elif mnemonic == "mtlo":
        write_regs.add(mips.UC_MIPS_REG_LO)
    elif ops:
        _add_reg(ops[0])

    return write_regs


# ---------------------------------------------------------------------------
# Modular Parsing & Assembly Stages
# ---------------------------------------------------------------------------

def _split_sections(
    asm_source: str,
    default_text_base: int,
    default_data_base: int,
) -> _ParsedSections:
    """Pass 1a: Splits raw MIPS source into `.data` and `.text` line lists."""
    section = "text"
    text_base = default_text_base
    data_base = default_data_base
    data_lines: list[str] = []
    text_lines: list[str] = []

    for raw_line in asm_source.splitlines():
        line = _strip_comments(raw_line)
        if not line:
            continue

        lower = line.lower()
        if lower.startswith(".data"):
            section = "data"
            parts = line.split()
            if len(parts) > 1:
                data_base = _parse_int(parts[1])
            continue
        if lower.startswith(".text"):
            section = "text"
            parts = line.split()
            if len(parts) > 1:
                text_base = _parse_int(parts[1])
            continue
        if lower.startswith((".globl", ".global")):
            continue

        if section == "data":
            data_lines.append(line)
        else:
            text_lines.append(line)

    return _ParsedSections(
        data_lines=data_lines,
        text_lines=text_lines,
        text_base=text_base,
        data_base=data_base,
    )


def _parse_data_section(
    data_lines: list[str],
    data_base: int,
) -> tuple[bytearray, dict[str, DataSymbol]]:
    """Pass 1b: Assembles `.data` directives into a binary buffer and symbol map."""
    cur_addr = data_base
    data_buffer = bytearray()
    data_symbols: dict[str, DataSymbol] = {}
    pending_label: str | None = None

    def _align_to(byte_boundary: int) -> None:
        nonlocal cur_addr
        while (cur_addr % byte_boundary) != 0:
            data_buffer.append(0)
            cur_addr += 1

    for line in data_lines:
        labels, rest = _extract_labels(line)
        if labels:
            pending_label = labels[-1]
        if not rest:
            continue

        parts = rest.split(None, 1)
        directive = parts[0].lower()
        args_str = parts[1].strip() if len(parts) > 1 else ""

        if directive == ".align":
            _align_to(1 << _parse_int(args_str))
            continue

        if directive == ".word":
            _align_to(4)
        elif directive == ".half":
            _align_to(2)

        start_addr = cur_addr
        words_written: list[int] = []

        if directive == ".word":
            for v in (_parse_int(tok) for tok in args_str.split(",") if tok.strip()):
                unsigned_32 = v & 0xFFFFFFFF
                data_buffer.extend(struct.pack(">I", unsigned_32))
                cur_addr += 4
                words_written.append(unsigned_32)
        elif directive == ".half":
            for v in (_parse_int(tok) for tok in args_str.split(",") if tok.strip()):
                data_buffer.extend(struct.pack(">H", v & 0xFFFF))
                cur_addr += 2
        elif directive == ".byte":
            for v in (_parse_int(tok) for tok in args_str.split(",") if tok.strip()):
                data_buffer.extend(struct.pack(">B", v & 0xFF))
                cur_addr += 1
        elif directive == ".space":
            n_bytes = _parse_int(args_str)
            data_buffer.extend(b"\x00" * n_bytes)
            cur_addr += n_bytes
        elif directive in (".asciiz", ".ascii"):
            m = re.search(r'"(.*)"', args_str)
            s = m.group(1).encode("utf-8").decode("unicode_escape") if m else ""
            raw_bytes = s.encode("latin1") + (b"\x00" if directive == ".asciiz" else b"")
            data_buffer.extend(raw_bytes)
            cur_addr += len(raw_bytes)

        if pending_label:
            data_symbols[pending_label] = DataSymbol(
                name=pending_label,
                address=start_addr,
                size=cur_addr - start_addr,
                directive=directive,
                initial_words=words_written,
            )
            pending_label = None

    return data_buffer, data_symbols


def _expand_pseudo_instruction(
    line: str,
    data_symbols: dict[str, DataSymbol],
) -> list[tuple[str, str]]:
    """Expands a MARS pseudo-instruction into 1 or 2 native MIPS32 instructions."""
    mnem, ops = _tokenize_instruction(line)

    if mnem == "move" and len(ops) == 2:
        return [(f"addu {ops[0]}, {ops[1]}, $zero", line)]

    if mnem == "li" and len(ops) == 2:
        imm = _parse_int(ops[1])
        if -32768 <= imm <= 32767:
            return [(f"addiu {ops[0]}, $zero, {imm}", line)]
        if 0 <= imm <= 0xFFFF:
            return [(f"ori {ops[0]}, $zero, {imm}", line)]
        hi, lo = (imm >> 16) & 0xFFFF, imm & 0xFFFF
        return [
            (f"lui {ops[0]}, {hi}", f"{line} [hi]"),
            (f"ori {ops[0]}, {ops[0]}, {lo}", f"{line} [lo]"),
        ]

    if mnem == "la" and len(ops) == 2:
        sym = ops[1]
        addr = data_symbols[sym].address if sym in data_symbols else _parse_int(sym)
        hi, lo = (addr >> 16) & 0xFFFF, addr & 0xFFFF
        if hi != 0 and lo == 0:
            return [(f"lui {ops[0]}, 0x{hi:x}", line)]
        if hi == 0:
            return [(f"ori {ops[0]}, $zero, 0x{lo:x}", line)]
        return [
            (f"lui {ops[0]}, 0x{hi:x}", f"{line} [hi]"),
            (f"ori {ops[0]}, {ops[0]}, 0x{lo:x}", f"{line} [lo]"),
        ]

    if mnem == "b" and len(ops) == 1:
        return [(f"beq $zero, $zero, {ops[0]}", line)]
    if mnem == "beqz" and len(ops) == 2:
        return [(f"beq {ops[0]}, $zero, {ops[1]}", line)]
    if mnem == "bnez" and len(ops) == 2:
        return [(f"bne {ops[0]}, $zero, {ops[1]}", line)]

    compound_branches: dict[str, tuple[bool, str]] = {
        "blt": (False, "bne"),
        "bge": (False, "beq"),
        "bgt": (True, "bne"),
        "ble": (True, "beq"),
    }
    if mnem in compound_branches and len(ops) == 3:
        swap_operands, br_mnem = compound_branches[mnem]
        lhs, rhs = (ops[1], ops[0]) if swap_operands else (ops[0], ops[1])
        return [
            (f"slt $at, {lhs}, {rhs}", f"{line} [cmp]"),
            (f"{br_mnem} $at, $zero, {ops[2]}", f"{line} [br]"),
        ]

    return [(line, line)]


def _expand_text_section(
    text_lines: list[str],
    text_base: int,
    data_symbols: dict[str, DataSymbol],
) -> tuple[list[tuple[str, str]], dict[str, int]]:
    """Pass 2: Records `.text` label addresses and expands pseudo-instructions."""
    expanded: list[tuple[str, str]] = []
    text_labels: dict[str, int] = {}

    for raw_line in text_lines:
        labels, inst_line = _extract_labels(raw_line)
        for lbl in labels:
            text_labels[lbl] = text_base + 4 * len(expanded)
        if inst_line:
            expanded.extend(_expand_pseudo_instruction(inst_line, data_symbols))

    return expanded, text_labels


def _resolve_branch_label(
    inst_str: str,
    inst_addr: int,
    text_labels: dict[str, int],
) -> tuple[str, int | None]:
    """Substitutes symbolic branch/jump targets with numeric offsets or addresses."""
    mnem, ops = _tokenize_instruction(inst_str)

    if mnem in ("beq", "bne") and len(ops) == 3 and ops[2] in text_labels:
        target = text_labels[ops[2]]
        return f"{mnem} {ops[0]}, {ops[1]}, {target - inst_addr}", target

    if mnem in ("blez", "bgtz", "bltz", "bgez") and len(ops) == 2 and ops[1] in text_labels:
        target = text_labels[ops[1]]
        return f"{mnem} {ops[0]}, {target - inst_addr}", target

    if mnem in ("j", "jal") and len(ops) == 1 and ops[0] in text_labels:
        target = text_labels[ops[0]]
        return f"{mnem} 0x{target:x}", target

    return inst_str, None


def _group_instructions_into_rules(
    instructions: list[model.MipsInstruction],
    text_labels: dict[str, int],
    steps_per_rule: int | Literal["basic_block"] = 1,
    stop_on_branch: bool = False,
) -> list[model.MipsInstructionRule]:
    """Packs `MipsInstruction`s into single or multi-instruction `MipsInstructionRule`s.

    Splits chunks at branch/jump boundaries and label target addresses so every
    control-flow entry point aligns with the start address of a `MipsInstructionRule`
    and every non-branch span executes in a single `mu.emu_start` call.
    """
    if steps_per_rule == 1:
        return [
            model.MipsInstructionRule(
                instructions=(insn,),
                steps=1,
                stop_on_branch=stop_on_branch,
            )
            for insn in instructions
        ]

    max_chunk = (
        len(instructions)
        if steps_per_rule == "basic_block"
        else max(1, int(steps_per_rule))
    )
    target_addrs: set[int] = set(text_labels.values())
    for insn in instructions:
        if insn.branch_target is not None:
            target_addrs.add(insn.branch_target)

    rules: list[model.MipsInstructionRule] = []
    current_chunk: list[model.MipsInstruction] = []

    for insn in instructions:
        # Start a new rule if `insn.address` is a label or branch target
        if current_chunk and insn.address in target_addrs:
            rules.append(
                model.MipsInstructionRule(
                    instructions=current_chunk,
                    steps=len(current_chunk),
                    stop_on_branch=stop_on_branch,
                )
            )
            current_chunk = []

        current_chunk.append(insn)

        # Flush the chunk at the end of a basic block (branch/jump) or max_chunk limit
        if insn.is_branch_or_jump or len(current_chunk) >= max_chunk:
            rules.append(
                model.MipsInstructionRule(
                    instructions=current_chunk,
                    steps=len(current_chunk),
                    stop_on_branch=stop_on_branch,
                )
            )
            current_chunk = []

    if current_chunk:
        rules.append(
            model.MipsInstructionRule(
                instructions=current_chunk,
                steps=len(current_chunk),
                stop_on_branch=stop_on_branch,
            )
        )

    return rules


def _compile_instruction_rules(
    expanded_instructions: list[tuple[str, str]],
    text_base: int,
    text_labels: dict[str, int],
    steps_per_rule: int | Literal["basic_block"] = 1,
    stop_on_branch: bool = False
) -> tuple[list[model.MipsInstructionRule], set[int]]:
    """Pass 3: Assembles instructions with Keystone, and packs them into `MipsInstructionRule` objects.
    """
    ks = Ks(KS_ARCH_MIPS, KS_MODE_MIPS32 + KS_MODE_BIG_ENDIAN)

    assembled_insns: list[model.MipsInstruction] = []
    auto_tracked_regs: set[int] = {mips.UC_MIPS_REG_PC}

    for idx, (inst_str, orig_str) in enumerate(expanded_instructions):
        inst_addr = text_base + 4 * idx
        resolved_asm, branch_target = _resolve_branch_label(
            inst_str, inst_addr, text_labels
        )

        encoding, _ = ks.asm(resolved_asm, addr=inst_addr)
        machine_bytes = bytes(encoding[:4])

        read_regs = extract_read_registers(inst_str)
        write_regs = extract_write_registers(inst_str)
        auto_tracked_regs.update(read_regs)
        auto_tracked_regs.update(write_regs)

        mnem, _ = _tokenize_instruction(inst_str)
        assembled_insns.append(
            model.MipsInstruction(
                address=inst_addr,
                asm_code=inst_str.strip(),
                machine_bytes=machine_bytes,
                source_line=orig_str.strip(),
                mnemonic=mnem,
                is_branch_or_jump=mnem in BRANCH_MNEMONICS,
                branch_target=branch_target,
                read_registers=frozenset(read_regs),
                write_registers=frozenset(write_regs),
            )
        )

    rules = _group_instructions_into_rules(
        instructions=assembled_insns,
        text_labels=text_labels,
        steps_per_rule=steps_per_rule,
        stop_on_branch=stop_on_branch,
    )
    return rules, auto_tracked_regs


def _init_unicorn_hardware(
    rules: list[model.MipsInstructionRule],
    data_buffer: bytearray,
    text_base: int,
    data_base: int,
    tracked_regs: set[int],
) -> Uc:
    """Pass 4: Initializes the persistent Unicorn instance and maps memory regions."""
    mu = Uc(UC_ARCH_MIPS, UC_MODE_MIPS32 + UC_MODE_BIG_ENDIAN)

    total_text_bytes = sum(len(r.machine_bytes) for r in rules)
    text_size = max(
        PAGE_SIZE, ((total_text_bytes + PAGE_SIZE) // PAGE_SIZE) * PAGE_SIZE
    )
    mu.mem_map(text_base & ~(PAGE_SIZE - 1), text_size)
    for rule in rules:
        mu.mem_write(rule.address, rule.machine_bytes)

    data_size = max(
        PAGE_SIZE, ((len(data_buffer) + PAGE_SIZE) // PAGE_SIZE) * PAGE_SIZE
    )
    mu.mem_map(data_base & ~(PAGE_SIZE - 1), data_size)
    if data_buffer:
        mu.mem_write(data_base, bytes(data_buffer))

    mu.mem_map(DEFAULT_STACK_BASE, DEFAULT_STACK_SIZE)
    if mips.UC_MIPS_REG_SP in tracked_regs:
        mu.reg_write(mips.UC_MIPS_REG_SP, DEFAULT_STACK_INIT)
    mu.reg_write(mips.UC_MIPS_REG_PC, text_base)

    return mu


def parse_and_load_mips(
    asm_source: str,
    text_base: int = DEFAULT_TEXT_ADDR,
    data_base: int = DEFAULT_DATA_ADDR,
    track_reads_as_causal: bool = True,
    track_pc_as_cell: bool = False,
    steps_per_rule: int | Literal["basic_block"] = 1,
    stop_on_branch: bool = False
) -> MipsProgramBundle:
    """Parses a MARS-style multiline MIPS string (`.data` and `.text`), initializes
    a persistent Unicorn emulator, auto-detects tracked registers and memory cells,
    and returns a ready-to-run `MipsProgramBundle`.
    """
    sections = _split_sections(asm_source, text_base, data_base)
    data_buffer, data_symbols = _parse_data_section(
        sections.data_lines, sections.data_base
    )
    expanded_text, text_labels = _expand_text_section(
        sections.text_lines, sections.text_base, data_symbols
    )
    rules, auto_tracked_regs = _compile_instruction_rules(
        expanded_instructions=expanded_text,
        text_base=sections.text_base,
        text_labels=text_labels,
        steps_per_rule=steps_per_rule,
        stop_on_branch=stop_on_branch
    )
    mu = _init_unicorn_hardware(
        rules=rules,
        data_buffer=data_buffer,
        text_base=sections.text_base,
        data_base=sections.data_base,
        tracked_regs=auto_tracked_regs,
    )

    initial_mem_addrs: set[int] = {
        sections.data_base + offset for offset in range(0, len(data_buffer), 4)
    }
    topology = model.MipsTopology(
        mu=mu,
        tracked_registers=auto_tracked_regs,
        initial_memory_addrs=initial_mem_addrs,
        track_reads_as_causal=track_reads_as_causal,
        track_pc_as_cell=track_pc_as_cell,
    )
    initial_space = model.MipsSpace(topology)
    initial_space.capture_snapshot()
    ruleset = model.MipsRuleSet(rules)
    total_text_bytes = sum(len(r.machine_bytes) for r in rules)

    return MipsProgramBundle(
        ruleset=ruleset,
        initial_space=initial_space,
        topology=topology,
        mu=mu,
        data_symbols=data_symbols,
        text_labels=text_labels,
        text_start=sections.text_base,
        text_end=sections.text_base + total_text_bytes,
        data_start=sections.data_base,
        data_end=sections.data_base + len(data_buffer),
    )
