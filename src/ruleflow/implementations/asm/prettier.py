"""
Compact, terminal-friendly Rich renderable builders for RuleFlow MIPS32
causal traces and hardware/memory state inspection.
"""
from typing import Sequence

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ruleflow.core.engine import Cell, Event, Flow
import ruleflow.implementations.asm.assembler as asm
import ruleflow.implementations.asm.model as m

_HEX_REGISTERS = {"$pc", "$sp", "$fp", "$gp", "$ra"}


def _clean_asm(asm_text: str) -> str:
    """Normalizes internal tabs and excessive spaces in an assembly string."""
    parts = asm_text.strip().split(None, 1)
    if len(parts) == 2:
        return f"{parts[0]:<6} {parts[1].strip()}"
    return asm_text.strip()


def _wrap_text_items(
    items: Sequence[Text],
    per_line: int = 4,
    indent: str = "",
) -> Text:
    """Joins `Text` items with commas, inserting a newline every `per_line` items."""
    if not items:
        return Text("None", style="dim")

    lines: list[Text] = []
    for i in range(0, len(items), per_line):
        chunk = items[i : i + per_line]
        line = Text(indent if i > 0 else "")
        line.append_text(Text(", ", style="dim").join(chunk))
        lines.append(line)
    return Text("\n").join(lines)


def capture_snapshot(bundle: asm.MipsProgramBundle) -> dict[int, int]:
    """Captures a `{location_id: raw_uint32}` snapshot of tracked registers and memory."""
    mu = bundle.mu
    topo = bundle.topology
    snap: dict[int, int] = {
        reg_id: mu.reg_read(reg_id) for reg_id in topo.tracked_registers
    }
    for addr in topo.tracked_memory:
        snap[addr] = topo.read_mem_word(addr)
    return snap


def resolve_symbol(
    addr: int,
    data_symbols: dict[str, asm.DataSymbol] | None = None,
) -> str:
    """Resolves a memory address to a `.data` symbol offset, stack offset, or hex address."""
    if data_symbols:
        for sym in data_symbols.values():
            if sym.address <= addr < sym.address + max(4, sym.size):
                offset = addr - sym.address
                return f"{sym.name}+{offset}" if offset else sym.name

    if asm.DEFAULT_STACK_BASE <= addr < asm.DEFAULT_STACK_BASE + asm.DEFAULT_STACK_SIZE:
        off = addr - asm.DEFAULT_STACK_INIT
        return f"stack{off:+d}" if off else "stack"

    return f"0x{addr:08x}"


def format_cell(
    cell: Cell,
    data_symbols: dict[str, asm.DataSymbol] | None = None,
) -> Text:
    """Formats a `Cell` into a styled `rich.text.Text` token."""
    text = Text()
    if cell.id in asm.REG_ID_TO_NAME:
        name = asm.REG_ID_TO_NAME[cell.id]
        val_str = (
            f"0x{cell.quanta:08x}"
            if name in _HEX_REGISTERS
            else str(asm.to_signed_32(cell.quanta))
        )
        text.append(name, style="bold cyan")
    else:
        sym = resolve_symbol(cell.id, data_symbols)
        val_str = str(asm.to_signed_32(cell.quanta))
        text.append(f"MEM[{sym}]", style="bold magenta")

    text.append("=", style="dim")
    text.append(val_str, style="bold white")
    text.append(f"(g{cell.gen})", style="dim")
    return text


def format_state(
    space: m.MipsSpace,
    include_memory: bool = True,
    data_symbols: dict[str, asm.DataSymbol] | None = None,
    per_line: int = 4,
) -> Text:
    """Formats a `MipsSpace` snapshot into a neatly wrapped multi-line `Text` block."""
    reg_items: list[Text] = []
    mem_items: list[Text] = []

    for loc_id, cell in sorted(space.snapshot.items()):
        if loc_id in asm.REG_ID_TO_NAME:
            reg_items.append(format_cell(cell, data_symbols))
        elif include_memory:
            mem_items.append(format_cell(cell, data_symbols))

    lines: list[Text] = []
    if reg_items:
        reg_line = Text("REG: ", style="bold cyan")
        reg_line.append_text(_wrap_text_items(reg_items, per_line=per_line, indent="     "))
        lines.append(reg_line)
    if mem_items:
        mem_line = Text("MEM: ", style="bold magenta")
        mem_line.append_text(_wrap_text_items(mem_items, per_line=per_line, indent="     "))
        lines.append(mem_line)

    return Text("\n").join(lines) if lines else Text("Empty", style="dim")


m.MipsSpace.__rich__ = format_state  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Granular Component Builders
# ---------------------------------------------------------------------------

def build_tracked_registers_panel(
    bundle: asm.MipsProgramBundle
) -> Panel:
    """Builds a compact `Panel` listing auto-detected tracked registers."""
    topo = bundle.topology
    reg_names = [asm.REG_ID_TO_NAME[r] for r in sorted(topo.tracked_registers)]

    reg_text = Text()
    reg_text.append(f"Tracked Registers ({len(reg_names)}): ", style="bold cyan")
    reg_text.append_text(
        Text(", ", style="dim").join(Text(r, style="bold yellow") for r in reg_names)
    )
    reg_text.append("   │   Causal Reads: ", style="bold cyan")
    reg_text.append(str(topo.track_reads_as_causal), style="bold white")
    reg_text.append("   │   Track $pc: ", style="bold cyan")
    reg_text.append(str(topo.track_pc_as_cell), style="bold white")

    return Panel(
        reg_text,
        title="[bold white]Configuration[/]",
        border_style="cyan",
        expand=False,
    )


def build_data_symbols_table(
    bundle: asm.MipsProgramBundle
) -> Table:
    """Builds a `Table` of initialized `.data` section symbols."""
    sym_table = Table(
        title=".data Symbols",
        box=box.ROUNDED,
        header_style="bold magenta",
        padding=(0, 1),
        collapse_padding=True,
        expand=False,
    )
    sym_table.add_column("Symbol", style="bold magenta", no_wrap=True)
    sym_table.add_column("Address", style="cyan", no_wrap=True)
    sym_table.add_column("Directive", style="dim", no_wrap=True)
    sym_table.add_column("Bytes", justify="right", no_wrap=True)
    sym_table.add_column("Initial Words (Signed)", style="green")

    for sym_name, sym in bundle.data_symbols.items():
        signed_words = [asm.to_signed_32(w) for w in sym.initial_words]
        sym_table.add_row(
            sym_name,
            f"0x{sym.address:08x}",
            sym.directive,
            str(sym.size),
            str(signed_words),
        )
    return sym_table


def build_rules_table(
    bundle: asm.MipsProgramBundle,
) -> Table:
    """Builds a `Table` of compiled `MipsInstructionRule`s in `.text`."""
    rules = [
        r for r in bundle.ruleset.rules if isinstance(r, m.MipsInstructionRule)
    ]
    total_insns = sum(len(r.instructions) for r in rules)

    rule_table = Table(
        title=f".text Rules ({len(rules)} Rules / {total_insns} Instructions)",
        box=box.ROUNDED,
        show_lines=any(len(r.instructions) > 1 for r in rules),
        header_style="bold blue",
        padding=(0, 1),
        collapse_padding=True,
        expand=False,
    )
    rule_table.add_column("Rule", justify="right", style="bold magenta", no_wrap=True)
    rule_table.add_column("Address", style="cyan", no_wrap=True)
    rule_table.add_column("Machine Bytes", style="dim", no_wrap=True)
    rule_table.add_column("Native MIPS32", style="bold white", min_width=26, no_wrap=True)
    rule_table.add_column("Original Source", style="yellow", min_width=24, no_wrap=True)
    rule_table.add_column("Steps", justify="right", style="bold green", no_wrap=True)

    for idx, r in enumerate(rules):
        addrs = "\n".join(f"0x{ins.address:08x}" for ins in r.instructions)
        hex_bytes = "\n".join(ins.machine_bytes.hex(" ") for ins in r.instructions)
        native_asm = "\n".join(_clean_asm(ins.asm_code) for ins in r.instructions)
        orig_src = "\n".join(_clean_asm(ins.source_line) for ins in r.instructions)
        rule_table.add_row(
            str(idx),
            addrs,
            hex_bytes,
            native_asm,
            orig_src,
            str(r.steps),
        )
    return rule_table


def build_register_table(
    bundle: asm.MipsProgramBundle,
    prev_snapshot: dict[int, int] | None = None,
    title: str = "Registers"
) -> Table:
    """Builds a top-to-bottom `Table` of register values with optional diff highlighting."""
    mu = bundle.mu
    tracked = sorted(bundle.topology.tracked_registers)

    reg_table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold cyan",
        padding=(0, 1),
        collapse_padding=True,
        expand=False,
    )
    reg_table.add_column("Reg", style="bold cyan", no_wrap=True)
    reg_table.add_column("Hex", style="white", no_wrap=True)
    reg_table.add_column("Signed", justify="right", style="green", no_wrap=True)
    reg_table.add_column("Gen", justify="right", style="dim", no_wrap=True)

    for reg_id in tracked:
        name = asm.REG_ID_TO_NAME.get(reg_id, f"reg_{reg_id}")
        val = mu.reg_read(reg_id)
        cell = bundle.topology.get_cell(reg_id)
        signed_val = asm.to_signed_32(val)

        changed = prev_snapshot is not None and prev_snapshot.get(reg_id, val) != val
        if changed and prev_snapshot is not None:
            prev_val = prev_snapshot[reg_id]
            if name == "$pc":
                hex_str = f"0x{prev_val:08x}→0x{val:08x}"
                signed_str = "-"
            else:
                hex_str = f"0x{val:08x}"
                signed_str = f"{asm.to_signed_32(prev_val)}→{signed_val}"
            style = "bold yellow"
        else:
            hex_str = f"0x{val:08x}"
            signed_str = "-" if name == "$pc" else str(signed_val)
            style = ""

        reg_table.add_row(
            Text(name, style=style or "bold cyan"),
            Text(hex_str, style=style or "white"),
            Text(signed_str, style=style or "green"),
            Text(f"g{cell.gen}", style=style or "dim"),
        )

    return reg_table


def build_memory_dump_table(
    bundle: asm.MipsProgramBundle,
    prev_snapshot: dict[int, int] | None = None,
    title: str = "Tracked Memory"
) -> Table:
    """Builds a top-to-bottom `Table` of all auto-tracked memory words."""
    topo = bundle.topology
    tracked_addrs = sorted(topo.tracked_memory)

    mem_table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold magenta",
        padding=(0, 1),
        collapse_padding=True,
        expand=False,
    )
    mem_table.add_column("Address", style="cyan", no_wrap=True)
    mem_table.add_column("Location", style="bold magenta", no_wrap=True)
    mem_table.add_column("Hex", style="white", no_wrap=True)
    mem_table.add_column("Signed", justify="right", style="bold green", no_wrap=True)
    mem_table.add_column("Gen", justify="right", style="dim", no_wrap=True)

    if not tracked_addrs:
        mem_table.add_row("-", "None", "-", "-", "-")
        return mem_table

    for addr in tracked_addrs:
        val = topo.read_mem_word(addr)
        cell = topo.get_cell(addr)
        signed_val = asm.to_signed_32(val)
        label = resolve_symbol(addr, bundle.data_symbols)

        changed = (
            prev_snapshot is not None
            and (addr not in prev_snapshot or prev_snapshot[addr] != val)
        )
        if changed and prev_snapshot is not None:
            if addr not in prev_snapshot:
                signed_str = f"(new) {signed_val}"
            else:
                prev_sint = asm.to_signed_32(prev_snapshot[addr])
                signed_str = (
                    f"{prev_sint}→{signed_val}"
                    if prev_sint != signed_val
                    else str(signed_val)
                )
            style = "bold yellow"
        else:
            signed_str = str(signed_val)
            style = ""

        mem_table.add_row(
            Text(f"0x{addr:08x}", style=style or "cyan"),
            Text(label, style=style or "bold magenta"),
            Text(f"0x{val:08x}", style=style or "white"),
            Text(signed_str, style=style or "bold green"),
            Text(f"g{cell.gen}", style=style or "dim"),
        )

    return mem_table


# ---------------------------------------------------------------------------
# Top-Level Composite Builders
# ---------------------------------------------------------------------------

def print_bundle_summary(
    bundle: asm.MipsProgramBundle,
    console: Console | None = None,
) -> Group:
    """Returns a `Group` summarizing registers, `.data` symbols, and `.text` rules."""
    renderables: list[RenderableType] = [build_tracked_registers_panel(bundle)]
    if bundle.data_symbols:
        renderables.append(build_data_symbols_table(bundle))
    renderables.append(build_rules_table(bundle))

    group = Group(*renderables)
    if console is not None:
        console.print(group)
    return group


def print_full_hardware_state(
    bundle: asm.MipsProgramBundle,
    prev_snapshot: dict[int, int] | None = None,
    include_registers: bool = True,
    include_memory: bool = True,
    title: str | None = None,
    console: Console | None = None,
) -> Group:
    """Returns a `Group` with auto-tracked register and memory tables."""
    prefix = f"{title} — " if title else ""
    renderables: list[RenderableType] = []

    if include_registers:
        renderables.append(
            build_register_table(
                bundle,
                prev_snapshot=prev_snapshot,
                title=f"{prefix}Registers",
            )
        )
    if include_memory:
        renderables.append(
            build_memory_dump_table(
                bundle,
                prev_snapshot=prev_snapshot,
                title=f"{prefix}Tracked Memory",
            )
        )

    group = Group(*renderables)
    if console is not None:
        console.print(group)
    return group


def print_causal_trace(
    flow: Flow,
    bundle: asm.MipsProgramBundle,
    event_range: slice | None = None,
    console: Console | None = None,
) -> Table:
    """Returns a well-proportioned `Table` of the causal execution trace."""
    events: Sequence[Event] = (
        flow.events[event_range] if event_range is not None else flow.events
    )

    if events:
        t0, t1 = events[0].time, events[-1].time
        range_str = f"Step {t0}" if t0 == t1 else f"Steps {t0}..{t1}"
    else:
        last_t = flow.events[-1].time if flow.events else 0
        range_str = f"No New Steps @ {last_t}"

    trace_table = Table(
        title=f"Causal Trace ({range_str})",
        box=box.ROUNDED,
        show_lines=True,
        header_style="bold white on dark_blue",
        padding=(0, 1),
        collapse_padding=True,
        expand=False,
    )
    trace_table.add_column("Step", justify="right", style="bold cyan", no_wrap=True)
    trace_table.add_column("Depth", justify="right", style="magenta", no_wrap=True)
    trace_table.add_column(
        "Executed Instruction(s)", style="white", min_width=28, no_wrap=True
    )
    trace_table.add_column("Deps", style="yellow", no_wrap=True)
    trace_table.add_column("Causal Cell Deltas", style="white")

    if not events:
        trace_table.add_row(
            "-",
            "-",
            Text("Inert (no instructions executed)", style="dim italic"),
            "-",
            Text("None", style="dim"),
        )
        if console is not None:
            console.print(trace_table)
        return trace_table

    for event in events:
        if event.time == 0:
            init_space = next(event.spaces)
            init_text = (
                format_state(init_space, data_symbols=bundle.data_symbols)
                if isinstance(init_space, m.MipsSpace)
                else Text(str(init_space), style="dim")
            )
            trace_table.add_row(
                "0",
                str(event.causal_distance_to_creation),
                Text("Initial Space", style="bold green"),
                "-",
                init_text,
            )
            continue

        for ds in event.space_deltas:
            rule = ds.rule
            assert isinstance(rule, m.MipsInstructionRule)
            deps = sorted(set(event.causally_connected_events))
            deps_str = ",".join(map(str, deps)) if deps else "-"

            out_space = ds.output_space[0]
            gen = (
                out_space.topology.gen
                if isinstance(out_space, m.MipsSpace)
                else event.time
            )
            exec_insns = rule.execution_history.get(gen, list(rule.instructions))

            inst_text = Text()
            if len(exec_insns) == 1:
                ins = exec_insns[0]
                inst_text.append(f"0x{ins.address:08x}", style="cyan")
                inst_text.append(": ", style="dim")
                inst_text.append(_clean_asm(ins.source_line), style="bold white")
            else:
                inst_text.append(
                    f"Block @ 0x{rule.address:08x} ({len(exec_insns)} insts):",
                    style="bold magenta",
                )
                for ins in exec_insns:
                    inst_text.append(f"\n  0x{ins.address:08x}", style="cyan")
                    inst_text.append(": ", style="dim")
                    inst_text.append(_clean_asm(ins.source_line), style="white")

            delta_lines: list[Text] = []
            for dc in ds.cell_deltas:
                unchanged_ids = {
                    d.id
                    for d in dc.destroyed_cells
                    for n in dc.new_cells
                    if d.id == n.id and d.quanta == n.quanta and d.gen == n.gen
                }
                created = [
                    format_cell(n, bundle.data_symbols)
                    for n in dc.new_cells
                    if n.id not in unchanged_ids
                ]
                destroyed = [
                    format_cell(d, bundle.data_symbols)
                    for d in dc.destroyed_cells
                    if d.id not in unchanged_ids
                ]
                read_only = [
                    format_cell(d, bundle.data_symbols)
                    for d in dc.destroyed_cells
                    if d.id in unchanged_ids
                ]

                if created:
                    line = Text("[+] ", style="bold green")
                    line.append_text(_wrap_text_items(created, per_line=4, indent="    "))
                    delta_lines.append(line)
                if destroyed:
                    line = Text("[-] ", style="bold red")
                    line.append_text(_wrap_text_items(destroyed, per_line=4, indent="    "))
                    delta_lines.append(line)
                if read_only:
                    line = Text("[?] ", style="bold blue")
                    line.append_text(_wrap_text_items(read_only, per_line=4, indent="    "))
                    delta_lines.append(line)

            deltas_renderable = (
                Text("\n").join(delta_lines)
                if delta_lines
                else Text("None", style="dim")
            )

            trace_table.add_row(
                str(event.time),
                str(event.causal_distance_to_creation),
                inst_text,
                deps_str,
                deltas_renderable,
            )

    if console is not None:
        console.print(trace_table)
    return trace_table
