"""
MIPS32 assembly execution and causal analysis module for RuleFlow.

Bridges the Unicorn CPU Emulator and Keystone Assembler with the RuleFlow
engine (`engine.py`), encapsulating single or multi-instruction MIPS blocks as
`MipsInstructionRule` objects inside a `MipsRuleSet` while maintaining a
persistent hardware instance inside `MipsTopology`.
"""
from copy import copy
from dataclasses import dataclass
import re
from typing import Any, Iterator, Sequence

from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, Uc
import unicorn.mips_const as mips

from ruleflow.core.engine import (
    Cell,
    DeltaCell,
    DeltaSpace,
    Rule,
    RuleMatch,
    RuleSet,
    SpaceState,
)
import ruleflow.implementations.asm.assembler as asm


@dataclass
class MemoryAccessRecord:
    """Captures a runtime memory read or write intercepted by Unicorn hooks."""
    access_type: str  # 'READ' or 'WRITE'
    address: int
    size: int
    old_value: int
    new_value: int


@dataclass(frozen=True)
class MipsInstruction:
    """Represents a single assembled 4-byte MIPS32 instruction within a rule."""
    address: int
    asm_code: str
    machine_bytes: bytes
    source_line: str
    mnemonic: str
    is_branch_or_jump: bool
    branch_target: int | None = None
    read_registers: frozenset[int] = frozenset()
    write_registers: frozenset[int] = frozenset()


class MipsTopology:
    """Unicorn-backed Topology that tracks causal Cells across instructions.

    Maintains a single persistent Unicorn (`Uc`) instance while tracking active
    `Cell` objects keyed by location ID (Unicorn register constant or 4-byte
    aligned memory address).
    """

    def __init__(
        self,
        mu: Uc,
        tracked_registers: set[int] | None = None,
        initial_memory_addrs: set[int] | None = None,
        track_reads_as_causal: bool = True,
        track_pc_as_cell: bool = False,
    ) -> None:
        self.mu: Uc = mu
        self.gen: int = 0
        self.track_reads_as_causal: bool = track_reads_as_causal
        self.track_pc_as_cell: bool = track_pc_as_cell

        self.tracked_registers: set[int] = set(tracked_registers or [])
        self.tracked_registers.add(mips.UC_MIPS_REG_PC)

        self.tracked_memory: set[int] = set(initial_memory_addrs or [])
        self.active_cells: dict[int, Cell] = {}
        self.mem_access_log: list[MemoryAccessRecord] = []

        # Seed $pc (and $sp if tracked) at generation 0
        pc_val = self.mu.reg_read(mips.UC_MIPS_REG_PC)
        self.active_cells[mips.UC_MIPS_REG_PC] = Cell(
            quanta=pc_val, gen=0, id=mips.UC_MIPS_REG_PC
        )
        if mips.UC_MIPS_REG_SP in self.tracked_registers:
            sp_val = self.mu.reg_read(mips.UC_MIPS_REG_SP)
            self.active_cells[mips.UC_MIPS_REG_SP] = Cell(
                quanta=sp_val, gen=0, id=mips.UC_MIPS_REG_SP
            )

        # Populate generation-0 Cells for pre-initialized .data memory words
        for addr in sorted(self.tracked_memory):
            val = self.read_mem_word(addr)
            self.active_cells[addr] = Cell(quanta=val, gen=0, id=addr)

        # Attach Unicorn memory hooks to auto-detect runtime memory reads/writes
        self.mu.hook_add(UC_HOOK_MEM_WRITE, self._on_mem_write)
        self.mu.hook_add(UC_HOOK_MEM_READ, self._on_mem_read)

    def _on_mem_write(
        self, uc: Uc, access: int, address: int, size: int, value: int, user_data: Any
    ) -> None:
        """Unicorn callback triggered immediately before a memory write occurs."""
        aligned_addr = address & ~0x3
        self.tracked_memory.add(aligned_addr)
        old_val = self.read_mem_word(aligned_addr)

        if size == 4 and address == aligned_addr:
            new_val = value & 0xFFFFFFFF
        else:
            raw = bytearray(uc.mem_read(aligned_addr, 4))
            offset = address - aligned_addr
            val_bytes = value.to_bytes(size, byteorder="big", signed=(value < 0))
            raw[offset : offset + size] = val_bytes
            new_val = int.from_bytes(raw, byteorder="big")

        self.mem_access_log.append(
            MemoryAccessRecord("WRITE", aligned_addr, size, old_val, new_val)
        )

    def _on_mem_read(
        self, uc: Uc, access: int, address: int, size: int, value: int, user_data: Any
    ) -> None:
        """Unicorn callback triggered when an instruction reads from data/stack memory."""
        aligned_addr = address & ~0x3
        self.tracked_memory.add(aligned_addr)
        cur_val = self.read_mem_word(aligned_addr)
        if aligned_addr not in self.active_cells:
            self.active_cells[aligned_addr] = Cell(
                quanta=cur_val, gen=0, id=aligned_addr
            )

        self.mem_access_log.append(
            MemoryAccessRecord("READ", aligned_addr, size, cur_val, cur_val)
        )

    def read_mem_word(self, address: int) -> int:
        """Reads a 32-bit big-endian unsigned integer from Unicorn memory."""
        raw = self.mu.mem_read(address, 4)
        return int.from_bytes(raw, byteorder="big")

    def clear_access_log(self) -> None:
        """Clears the per-rule memory access log prior to stepping."""
        self.mem_access_log.clear()

    @property
    def as_cells(self) -> Iterator[Cell]:
        """Yields all currently active register and memory Cells."""
        return iter(self.active_cells.values())

    def get_cell(self, index: Any) -> Cell:
        """Retrieves a specific Cell by register constant or memory address."""
        if index in self.active_cells:
            return self.active_cells[index]
        if index < 0x1000:
            val = self.mu.reg_read(index)
        else:
            val = self.read_mem_word(index)
        return Cell(quanta=val, gen=0, id=index)

    def get_cells(self, index: Sequence[int]) -> Iterator[Cell]:
        """Retrieves a sequence of Cells by their indices."""
        for idx in index:
            yield self.get_cell(idx)

    def next_gen(self) -> MipsTopology:
        """Advances the causal generation counter on the persistent topology."""
        self.gen += 1
        return self


class MipsSpace(SpaceState):
    """SpaceState wrapper around `MipsTopology`.

    Records a snapshot of `active_cells` at each generation so
    historical spaces across `Flow.events` remain inspectable.
    """

    def __init__(self, topology: MipsTopology) -> None:
        self._topology: MipsTopology = topology
        self.snapshot: dict[int, Cell] = topology.active_cells

    @property
    def topology(self) -> MipsTopology:
        return self._topology

    def get_pc(self) -> int:
        """Returns the current Program Counter directly from the Unicorn CPU."""
        return self._topology.mu.reg_read(mips.UC_MIPS_REG_PC)

    def capture_snapshot(self) -> None:
        """Updates this space's cell snapshot after a rule executes."""
        self.snapshot = copy(self.snapshot)

    def next_gen(self) -> MipsSpace:
        """Advances the topology generation and returns a new MipsSpace wrapper."""
        return MipsSpace(self._topology.next_gen())


class MipsInstructionRule(Rule):
    """Encapsulates one or more contiguous MIPS32 instructions starting at `self.address`.

    Supports two complementary ways of executing multiple instructions atomically:
    1. **Multi-instruction blocks (`self.instructions`)**: A single rule directly owns
       a contiguous sequence of `MipsInstruction`s (such as a basic block or an N-instruction
       chunk). `_step_hardware` executes the entire contiguous non-branch span in one
       `mu.emu_start(start_addr, end_addr)` call (`count=0`), allowing QEMU to compile
       and cache the block as a single native Translation Block (TB).
    2. **Dynamic step count (`self.steps`)**: If `self.steps` is set larger than
       `len(self.instructions)`, `_step_hardware` continues across subsequent blocks in
       the parent `MipsRuleSet` within the same atomic rule application.
    """

    def __init__(
        self,
        address: int | None = None,
        asm_code: str | None = None,
        machine_bytes: bytes | None = None,
        source_line: str | None = None,
        branch_target: int | None = None,
        steps: int | None = None,
        stop_on_branch: bool = False,
        read_registers: set[int] | None = None,
        write_registers: set[int] | None = None,
        instructions: Sequence[MipsInstruction] | None = None,
    ) -> None:
        super().__init__()

        if instructions is not None:
            if not instructions:
                raise ValueError("MipsInstructionRule requires at least one MipsInstruction.")
            self.instructions: tuple[MipsInstruction, ...] = tuple(instructions)
        else:
            if address is None or asm_code is None or machine_bytes is None:
                raise ValueError(
                    "Provide either `instructions` or `(address, asm_code, machine_bytes)`."
                )
            clean_asm = asm_code.strip()
            mnemonic = clean_asm.split()[0].lower() if clean_asm else "nop"
            r_regs = (
                frozenset(read_registers)
                if read_registers is not None
                else frozenset(asm.extract_read_registers(clean_asm))
            )
            w_regs = (
                frozenset(write_registers)
                if write_registers is not None
                else frozenset(asm.extract_write_registers(clean_asm))
            )
            single_insn = MipsInstruction(
                address=address,
                asm_code=clean_asm,
                machine_bytes=machine_bytes,
                source_line=(source_line or clean_asm).strip(),
                mnemonic=mnemonic,
                is_branch_or_jump=mnemonic in asm.BRANCH_MNEMONICS,
                branch_target=branch_target,
                read_registers=r_regs,
                write_registers=w_regs,
            )
            self.instructions = (single_insn,)

        self.address: int = self.instructions[0].address
        self.end_address: int = self.instructions[-1].address + 4
        self.machine_bytes: bytes = b"".join(ins.machine_bytes for ins in self.instructions)
        self.asm_code: str = " ; ".join(ins.asm_code for ins in self.instructions)
        self.source_line: str = " ; ".join(
            dict.fromkeys(ins.source_line for ins in self.instructions)
        )

        self.mnemonic: str = self.instructions[-1].mnemonic
        self.branch_target: int | None = self.instructions[-1].branch_target
        self.is_branch_or_jump: bool = any(
            ins.is_branch_or_jump for ins in self.instructions
        )
        self._is_single_terminal_branch: bool = (
            all(not ins.is_branch_or_jump for ins in self.instructions[:-1])
            and self.instructions[-1].is_branch_or_jump
        )

        # Precompute aggregate register dependencies across all owned instructions
        self.read_registers: set[int] = set().union(
            *(ins.read_registers for ins in self.instructions)
        )
        self.write_registers: set[int] = set().union(
            *(ins.write_registers for ins in self.instructions)
        )

        # Default `steps` to the number of instructions encapsulated by this rule
        self.steps: int = max(1, steps if steps is not None else len(self.instructions))
        self.stop_on_branch: bool = stop_on_branch

        # Back-reference linked by MipsRuleSet for cross-block lookahead when steps > len(instructions)
        self.ruleset: MipsRuleSet | None = None

        # Records the exact sequence of MipsInstructions executed per generation (`gen -> list[MipsInstruction]`)
        self.execution_history: dict[int, list[MipsInstruction]] = {}
        self.last_executed_instructions: list[MipsInstruction] = list(self.instructions)

    @classmethod
    def from_instructions(
        cls,
        instructions: Sequence[MipsInstruction],
        steps: int | None = None,
        stop_on_branch: bool = False,
    ) -> MipsInstructionRule:
        """Constructs a multi-instruction rule directly from a sequence of `MipsInstruction`s."""
        return cls(
            instructions=instructions,
            steps=steps,
            stop_on_branch=stop_on_branch,
        )

    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        """Matches when an active `MipsSpace` has its Program Counter at `self.address`."""
        matches: list[RuleMatch] = []
        for space in spaces:
            if isinstance(space, MipsSpace) and space.get_pc() == self.address:
                matches.append(
                    RuleMatch(
                        space=space,
                        matches=[(self.address,)],
                        conflicts=set(),
                        metadata=self.asm_code,
                    )
                )
        return matches

    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        """Executes the rule's instructions on Unicorn and builds an atomic `DeltaSpace`."""
        space_deltas: list[DeltaSpace] = []
        for match in rule_matches:
            input_space = match.space
            if not isinstance(input_space, MipsSpace):
                continue

            output_space = input_space.next_gen()
            topo = output_space.topology
            mu = topo.mu
            current_gen = topo.gen

            # 1. Snapshot pre-execution state prior to running the hardware burst
            topo.clear_access_log()
            pre_active_cells: dict[int, Cell] = copy(topo.active_cells)
            pre_regs: dict[int, int] = {
                reg_id: mu.reg_read(reg_id) for reg_id in topo.tracked_registers
            }

            # 2. Execute the instruction block(s) in Unicorn via `_step_hardware`
            executed_insns = self._step_hardware(mu)
            self.last_executed_instructions = executed_insns
            self.execution_history[current_gen] = executed_insns

            if len(executed_insns) == len(self.instructions) and all(
                a is b for a, b in zip(executed_insns, self.instructions)
            ):
                combined_read_regs = self.read_registers
                combined_write_regs = self.write_registers
            else:
                combined_read_regs = set().union(
                    *(ins.read_registers for ins in executed_insns)
                )
                combined_write_regs = set().union(
                    *(ins.write_registers for ins in executed_insns)
                )

            # 3. Diff registers and memory against pre-burst state to construct DeltaCells
            destroyed_cells: list[Cell] = []
            new_cells: list[Cell] = []
            handled_locs: set[int] = set()

            # 3a. Process tracked registers
            for reg_id in sorted(topo.tracked_registers):
                if reg_id == mips.UC_MIPS_REG_PC and not topo.track_pc_as_cell:
                    topo.active_cells[reg_id] = Cell(
                        quanta=mu.reg_read(reg_id), gen=current_gen, id=reg_id
                    )
                    continue

                post_val = mu.reg_read(reg_id)
                existed_before = reg_id in pre_active_cells
                old_cell = pre_active_cells.get(reg_id)

                was_written = (reg_id in combined_write_regs) or (
                    pre_regs[reg_id] != post_val
                )
                was_read = topo.track_reads_as_causal and (
                    reg_id in combined_read_regs
                )

                if was_written:
                    if existed_before and old_cell is not None:
                        destroyed_cells.append(old_cell)
                    new_cell = Cell(quanta=post_val, gen=current_gen, id=reg_id)
                    new_cells.append(new_cell)
                    topo.active_cells[reg_id] = new_cell
                    handled_locs.add(reg_id)
                elif was_read and existed_before and old_cell is not None:
                    destroyed_cells.append(old_cell)
                    new_cells.append(old_cell)
                    handled_locs.add(reg_id)

            # 3b. Consolidate intercepted memory reads and writes across all executed steps
            mem_order: list[int] = []
            mem_writes: dict[int, int] = {}
            mem_reads: set[int] = set()

            for record in topo.mem_access_log:
                addr = record.address
                if addr not in mem_writes and addr not in mem_reads:
                    mem_order.append(addr)
                if record.access_type == "WRITE":
                    mem_writes[addr] = record.new_value
                elif record.access_type == "READ":
                    mem_reads.add(addr)

            for addr in mem_order:
                if addr in handled_locs:
                    continue
                old_cell = pre_active_cells.get(addr) or topo.active_cells.get(addr)

                if addr in mem_writes:
                    if old_cell is not None and old_cell.gen > 0:
                        destroyed_cells.append(old_cell)
                    final_mem_val = topo.read_mem_word(addr)
                    new_cell = Cell(quanta=final_mem_val, gen=current_gen, id=addr)
                    new_cells.append(new_cell)
                    topo.active_cells[addr] = new_cell
                    handled_locs.add(addr)
                elif (
                    addr in mem_reads
                    and topo.track_reads_as_causal
                    and old_cell is not None
                ):
                    destroyed_cells.append(old_cell)
                    new_cells.append(old_cell)
                    handled_locs.add(addr)

            # 3c. Fallback to $pc transition if no data cells were touched (e.g. standalone `j`)
            if not destroyed_cells and not new_cells:
                old_pc_cell = Cell(
                    quanta=pre_regs[mips.UC_MIPS_REG_PC],
                    gen=max(0, current_gen - 1),
                    id=mips.UC_MIPS_REG_PC,
                )
                new_pc_cell = Cell(
                    quanta=mu.reg_read(mips.UC_MIPS_REG_PC),
                    gen=current_gen,
                    id=mips.UC_MIPS_REG_PC,
                )
                destroyed_cells.append(old_pc_cell)
                new_cells.append(new_pc_cell)

            output_space.capture_snapshot()
            delta_cell = DeltaCell(
                destroyed_cells=tuple(destroyed_cells),
                new_cells=tuple(new_cells),
            )
            space_deltas.append(
                DeltaSpace(
                    input_space=input_space,
                    output_space=(output_space,),
                    cell_deltas=(delta_cell,),
                    rule=self,
                )
            )

        return space_deltas

    def _lookup_insn(self, address: int) -> MipsInstruction | None:
        """Finds the `MipsInstruction` at `address` from this rule or the parent `MipsRuleSet`."""
        if self.address <= address < self.end_address:
            idx = (address - self.address) // 4
            if 0 <= idx < len(self.instructions):
                return self.instructions[idx]
        if self.ruleset is not None:
            return self.ruleset.addr_to_insn.get(address)
        return None

    def _step_hardware(self, mu: Uc) -> list[MipsInstruction]:
        """Executes this rule's instructions (up to `self.steps`) on Unicorn.

        Uses address-bounded `mu.emu_start(start_addr, end_addr)` calls (with
        `count=0`) across contiguous non-branch instruction ranges so QEMU
        compiles and caches the entire range as a single Translation Block (TB)
        without per-instruction counter hooks or repeated JIT teardowns.
        """
        # Fast Path 1: Contiguous non-branch multi-instruction rule
        if self.steps == len(self.instructions) and not self.is_branch_or_jump:
            mu.emu_start(self.address, self.end_address)
            mu.reg_write(mips.UC_MIPS_REG_PC, self.end_address)
            return list(self.instructions)

        # Fast Path 2: Contiguous basic-block rule ending with a single branch/jump
        if self.steps == len(self.instructions) and self._is_single_terminal_branch:
            branch_insn = self.instructions[-1]
            if len(self.instructions) > 1:
                mu.emu_start(self.address, branch_insn.address)
            self._step_branch_hardware(mu, branch_insn)
            return list(self.instructions)

        # General Path: Arbitrary `self.steps` (including cross-branch / multi-block bursts)
        steps_remaining = self.steps
        executed: list[MipsInstruction] = []
        cur_pc = self.address

        while steps_remaining > 0:
            cur_insn = self._lookup_insn(cur_pc)
            if cur_insn is None:
                break

            if cur_insn.is_branch_or_jump:
                self._step_branch_hardware(mu, cur_insn)
                executed.append(cur_insn)
                steps_remaining -= 1
                cur_pc = mu.reg_read(mips.UC_MIPS_REG_PC)
                if self.stop_on_branch:
                    break
                continue

            # Gather contiguous non-branch instructions up to `steps_remaining`
            batch: list[MipsInstruction] = [cur_insn]
            while len(batch) < steps_remaining:
                next_addr = cur_pc + 4 * len(batch)
                next_insn = self._lookup_insn(next_addr)
                if next_insn is None or next_insn.is_branch_or_jump:
                    break
                batch.append(next_insn)

            end_pc = cur_pc + 4 * len(batch)
            # Halt naturally at `end_pc` (`count=0`) so QEMU runs a single cached TB
            mu.emu_start(cur_pc, end_pc)
            mu.reg_write(mips.UC_MIPS_REG_PC, end_pc)

            executed.extend(batch)
            steps_remaining -= len(batch)
            cur_pc = end_pc

        return executed

    def _step_branch_hardware(
        self, mu: Uc, insn: MipsInstruction | None = None
    ) -> None:
        """Evaluates branch/jump target directly for single-cycle MARS semantics."""
        target_insn = insn or self.instructions[-1]
        next_pc = target_insn.address + 4
        parts = [
            p.strip() for p in re.split(r"[\s,]+", target_insn.asm_code) if p.strip()
        ]
        ops = parts[1:]

        if target_insn.mnemonic in ("jal", "jalr"):
            mu.reg_write(mips.UC_MIPS_REG_RA, target_insn.address + 4)

        if target_insn.mnemonic in ("jr", "jalr") and ops:
            src_reg = asm.MIPS_REG_MAP[ops[-1].lower()]
            next_pc = mu.reg_read(src_reg)
        elif (
            self._check_branch_taken(mu, target_insn)
            and target_insn.branch_target is not None
        ):
            next_pc = target_insn.branch_target

        mu.reg_write(mips.UC_MIPS_REG_PC, next_pc)

    def _check_branch_taken(
        self, mu: Uc, insn: MipsInstruction | None = None
    ) -> bool:
        """Evaluates whether a MIPS branch or jump instruction takes its target."""
        target_insn = insn or self.instructions[-1]
        mnem = target_insn.mnemonic
        if mnem in ("j", "jal", "jr", "jalr"):
            return True

        parts = [
            p.strip() for p in re.split(r"[\s,]+", target_insn.asm_code) if p.strip()
        ]
        ops = parts[1:]

        def _reg_signed(tok: str) -> int:
            return asm.to_signed_32(mu.reg_read(asm.MIPS_REG_MAP[tok.lower()]))

        if mnem == "beq" and len(ops) >= 2:
            return _reg_signed(ops[0]) == _reg_signed(ops[1])
        if mnem == "bne" and len(ops) >= 2:
            return _reg_signed(ops[0]) != _reg_signed(ops[1])
        if mnem == "blez" and ops:
            return _reg_signed(ops[0]) <= 0
        if mnem == "bgtz" and ops:
            return _reg_signed(ops[0]) > 0
        if mnem == "bltz" and ops:
            return _reg_signed(ops[0]) < 0
        if mnem == "bgez" and ops:
            return _reg_signed(ops[0]) >= 0
        return False


class MipsRuleSet(RuleSet):
    """RuleSet indexed by virtual instruction address for O(1) rule and instruction lookup."""

    def __init__(self, rules: list[MipsInstructionRule]) -> None:
        super().__init__(list(rules))
        self.addr_to_rule: dict[int, MipsInstructionRule] = {}
        self.addr_to_insn: dict[int, MipsInstruction] = {}
        for r in rules:
            r.ruleset = self
            self.addr_to_rule[r.address] = r
            for insn in r.instructions:
                self.addr_to_insn[insn.address] = insn
                if insn.address not in self.addr_to_rule:
                    self.addr_to_rule[insn.address] = r

    def configure_steps(
        self,
        steps: int = 1,
        stop_on_branch: bool = False,
        addresses: Sequence[int] | None = None,
    ) -> None:
        """Updates `steps` and `stop_on_branch` across all rules or selected addresses."""
        target_rules = (
            [self.addr_to_rule[a] for a in addresses if a in self.addr_to_rule]
            if addresses is not None
            else self.rules
        )
        for r in target_rules:
            if isinstance(r, MipsInstructionRule):
                r.steps = max(1, steps)
                r.stop_on_branch = stop_on_branch

    def apply(self, to_spaces: Sequence[SpaceState]) -> list[DeltaSpace]:
        """Applies the instruction rule matching each space's Program Counter."""
        space_deltas: list[DeltaSpace] = []
        for space in to_spaces:
            if not isinstance(space, MipsSpace):
                continue
            pc = space.get_pc()
            rule = self.addr_to_rule.get(pc)
            if rule is None or rule.disabled:
                continue
            matches = rule.match((space,))
            if matches:
                deltas = rule.apply(matches)
                if any(deltas):
                    space_deltas.extend(deltas)
        return space_deltas
