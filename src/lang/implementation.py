"""The implementation for 1D space that supports the language features.

Policy:
- Any multiways should have the search_buffer optimization disabled (Vec.enable_search_buffer(False)) so that it doesn't
become corrupt when branching (one state spawning two states). We have considered coding buffer branching logic...
however, that does not cover everything as Engine.RuleSet.apply() with group_break=False will not branch the buffer.
In the future, we may consider making the search_buffer branch-able (really, it is already possible by manually using Vec.search_buffer.copy()).

Future Considerations:
- We will need to create different implementations for higher dimensions spaces.
"""
from typing import Sequence, NamedTuple, Literal, cast, Iterator
from copy import deepcopy, copy
from lang.numerical_helpers import INF
from core.signals import Signal
from core.engine import (
    SpaceState1D as SpaceState,
    Cell,
    Rule as RuleABC,
    RuleMatch,
    DeltaSpace,
    DeltaCell
)


class Selector(NamedTuple):
    type: Literal["literal", "regex", "range"]
    selector: str | bytes | tuple[int, int]  # str | bytes is used for both literal and regex


class Target(NamedTuple):
    type: Literal["literal", "int"]
    target: Sequence[Cell] | int  # Sequence[Cell] is for most operations, Int for operations such as shifting.


class BaseRule(RuleABC):
    # ======== Signals ========
    # NOTE: time.sleep() can be used by the client to pause flow execution temporally (or play notes, etc.).
    on_applied: Signal = Signal()  # if the apply() function was called. The modified spaces is passed as Sequence[DeltaSpace] so that the client can test if the rule was effective.

    # the three following rules get the RuleMatch along with idx of the current match passed as arguments to the client.
    on_execution: Signal = Signal()
    on_branch: Signal = Signal()
    on_conflict: Signal = Signal()

    FLAG_ALIAS: dict[str, str] = {
        # IMPORTANT!!!: these must be kept up-to-date with the actual attributes.
        # ==== basic flags ====
        'd': 'disabled',
        'g': 'group',
        'gb': 'group_break',
        'a': 'always_apply',

        # ==== match() flags ====
        'sr': 'space_range',
        'mr': 'match_range',
        # offset
        # cmp

        # ==== apply() flags ====
        'nct': 'no_causality_tracking',
        'nib': 'no_initial_branch',
        'nds': 'no_delta_submit',
        'pl': 'parallel_execution_limit',
        'bl': 'branch_limit',
        'bo': 'branch_origin',
        # tso
        # crp
        'life': 'lifespan',
    }

    def __init__(self, selector: Sequence[Selector], target: Sequence[Target]):
        super().__init__()
        # Functionality Fields (you can have multiple selectors and multiple targets)
        self.selectors: Sequence[Selector] = selector  # used by self.match()
        self.target: Sequence[Target] = target  # used by self.apply()

        # Complex Functionality
        self.chain: list[BaseRule] = [self]  # so that multiple rules can be chained to this one. Each rule here is treated as though it is "self".
        self.is_in_chain: bool = False  # if this is true, this rule will be ignored as it is expected to run in a chain.

        # ======== Flags (that modify the internal rule behavior) ========
        # match() flags
        self.space_range: tuple[int, int] = (0, 1)  # the range of spaces that are matched
        self.match_range: tuple[int, int] = (0, 1)  # the range of matches if there are multiple matches
        self.offset: int = 0  # the offset to the index that selectors return.
        self.cmp: Literal["both", "og", "this", "ignore"] = "ignore"  # conflict marking protocol (if the second match conflicts with the first match, mark both as conflicts if mode='both', for instance, not only the second one.)

        # apply() flags
        self.no_causality_tracking: bool = False  # no cellular causality tracking (don't return delta cells)
        self.no_initial_branch: bool = False  # no initial branch the last space before executing rule (just modify last space) (can still be branched depending on `-pl` limit)
        self.no_delta_submit: bool = False  # if no new states are to be submitted (even if they do occur)
        self.parallel_execution_limit: int = 1  # parallel execution limit (how many times the rule can be executed per run without breaking into another branch).
        self.branch_limit: int = 0  # branch limit per run (how many branches can be created).
        self.branch_origin: Literal["prev", "current"] = "prev"  # does not apply to the first branch from previous event.
        self.crp: Literal["branch", "branch_nbl", "skip", "break", "ignore"] = "ignore"  # conflict resolution protocol. Note: at some point this could be extended to exclude BOTH conflicts, not just the one conflicting with the other.

        # rule life flags
        self.lifespan: int = INF  # how many times this rule is allowed to be successfully applied. This is the overall effect a rule can have before it dies.

        # stochastic flags  TODO: implement these
        self.p_seed: int | None = None  # determines the seed... if the outcome will be the same every time.
        self.p_match: int | None = None  # probability that a match will be counted.
        self.p_space: int | None = None  # probability that a space will be selected.
        self.p_apply: int | None = None  # probability that a rule will apply() at all.

        # Note that additional flags can be set in the syntax, however, they will have no meaning unless included in the control flow by subclassing and modifying particular rule.


    def __repr__(self):
        return f"{self.__class__.__name__}({[s.selector for s in self.selectors]}, {[t.target for t in self.target]})"

    def _conflict_detector(self, current_matches: list[tuple[int, int]], match: tuple[int, int]) -> set[int]:
        """helper that detects collisions between selectors"""
        this_idx: int = len(current_matches)  # the len will be the index of match
        conflicts: set[int] = set()
        start1, end1 = match
        for og_idx, m in enumerate(current_matches):
            start2, end2 = m
            if (start1 < start2 < end1 or start1 < end2 < end1
                    or start2 < start1 < end2 or start2 < end1 < end2):
                if self.crp == "this": conflicts.add(this_idx)
                elif self.crp == "og": conflicts.add(og_idx)
                elif self.cmp == "both":
                    conflicts.add(this_idx)
                    conflicts.add(og_idx)
                else:  # if "ignore"
                    continue
        return conflicts

    # noinspection PyMethodFirstArgAssignment
    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        top_self = self  # for og reference when we loop through self (comment out to show a great bug example when two universes don't evolve in parallel)
        if self.is_in_chain:
            return ()  # we do not run the rule outside the collective "self"
        out: list[RuleMatch] = []
        for i, space in enumerate(spaces):
            if self.space_range[0] > i:
                continue
            if i >= self.space_range[1]:
                break
            chained: list[BaseRule] = []
            matches: list[tuple[int, int]] = []
            conflicts: set[int] = set()
            for self in top_self.chain:
                if self.disabled:  # we must check if the rule has been disabled in case the rule is in a chain (has been merged)
                    continue
                for pattern in self.selectors:
                    finds: Iterator[tuple[int, int]]
                    if pattern.type in ('literal', 'regex'):
                        # finds = space.find(tuple(Cell(c) for c in pattern.selector))  # older slow way (before Vec containers)
                        # noinspection PyUnresolvedReferences
                        finds = space.cells.finditer(pattern.selector)  # FlowLang uses the Vec objects from the custom vec implementation for cells in the space states (look at the interpreter). These Vecs have builtin regex matching.
                    elif pattern.type == 'range':
                        finds = iter((pattern.selector,))
                    else: continue
                    for j, span in enumerate(finds):
                        if self.offset:
                            span = (span[0] + self.offset, span[1] + self.offset)
                        if self.match_range[0] > j:
                            continue
                        if j >= self.match_range[1]:
                            break
                        if self.cmp != 'ignore':
                            conflicts.update(self._conflict_detector(matches, span))
                        matches.append(span)
                        chained.append(self)  # these "line up" with the matches
            if matches:
                out.append(
                    RuleMatch(
                        space=space,
                        matches=matches,
                        conflicts=conflicts,
                        metadata=chained,  # we simply use this extra (and optional) metadata field to let .apply() know which rule in self.chain is tied to which match.
                    )
                )
        return out

    @staticmethod
    def _aggregate_DeltaCells(delta_cells: list[DeltaCell]) -> DeltaCell:
        """Helper function to aggregate many DeltaCells into a single DeltaCell"""
        if len(delta_cells) == 1:
            return delta_cells[0]
        destroyed_cells: list[Cell] = []
        new_cells: list[Cell] = []
        for delta_cell in delta_cells:
            destroyed_cells.extend(delta_cell.destroyed_cells)
            new_cells.extend(delta_cell.new_cells)
        return DeltaCell(destroyed_cells, new_cells)

    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: Sequence[Cell] | int | None) -> DeltaCell:
        raise NotImplementedError('A subclass must implement the correct modifier (e.g. `space.substitute(selector, deepcopy(target))`)')

    # noinspection PyMethodFirstArgAssignment
    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        top_self: BaseRule = self  # because self is reassigned when self has a chain of followers.
        modified_spaces: list[DeltaSpace] = []
        for rule_match in rule_matches:  # basically loop through all spaces
            # submitted updates
            submitted_spaces: list[SpaceState | None] = []
            submitted_cell_deltas: list[DeltaCell] = []  # list of (aggregated) DeltaCells that must align with the output space

            # state of the sim
            prev_space: SpaceState = cast(SpaceState, rule_match.space)
            current_space: SpaceState = prev_space if self.no_initial_branch else copy(prev_space)
            cell_deltas: list[DeltaCell] = []  # stack of the cell deltas that is cleared whenever delta space is submitted
            pl: int = 0  # parallel executions
            bl: int = 0  # branch executions
            matches_bound: int = len(rule_match.matches) - 1
            for idx, selector in enumerate(rule_match.matches):  # a "run" over the matches to the space.
                self: BaseRule = rule_match.metadata[idx]  # we need to treat each rule in the chain (specifically those with successful matches which are put in .metadata of the RuleMatch) as though they are "self"
                if self.target:
                    # noinspection PyUnresolvedReferences
                    target: Sequence[Cell] | int = self.target[idx % len(self.target)].target  # so that multiple targets are looped over...
                else:
                    target: None = None

                # handle the selector if it is a conflict
                if self.parallel_execution_limit > 1 and self.crp != 'ignore' and idx in rule_match.conflicts:
                    self.on_conflict.emit(self, rule_match, idx)
                    if self.crp in ('branch', 'branch_nbl'):
                        if self.crp == 'branch' and bl > self.branch_limit:
                            continue
                        branch: SpaceState = copy(prev_space) if self.branch_origin == 'prev' else copy(current_space)  # note: be careful when using branch_origin=current because of overwriting a conflict pair... just use with caution.
                        dc: DeltaCell = self._call_space_modifier(branch, selector, target)
                        submitted_spaces.append(
                            branch if not self.no_delta_submit else None
                        )
                        submitted_cell_deltas.append(
                            DeltaCell((), ()) if self.no_causality_tracking else dc
                        )
                    elif self.crp == 'skip':
                        continue  # just skip this selector
                    elif self.crp == 'break':
                        break
                    continue

                # apply operation
                cell_deltas.append(
                    self._call_space_modifier(current_space, selector, target)
                )
                pl += 1  # increment the parallel execution tracker

                # if pl is at max, submit modified space
                if pl == self.parallel_execution_limit or idx == matches_bound:  # if parallel execution limit is reached OR no more matches for the space
                    submitted_spaces.append(
                        current_space if not self.no_delta_submit else None
                    )
                    submitted_cell_deltas.append(
                        DeltaCell((), ()) if self.no_causality_tracking else self._aggregate_DeltaCells(cell_deltas)
                    )
                    pl = 0
                    cell_deltas.clear()
                    self.on_execution.emit(self, rule_match, idx)

                    # set the new current space (branch into another universe)
                    if bl != self.branch_limit:
                        current_space = copy(prev_space) if self.branch_origin == 'prev' else copy(current_space)  # note: be careful when using branch_origin=current because of overwriting a conflict pair... just use with caution.
                        bl += 1
                        self.on_branch.emit(self, rule_match, idx)
                    else:
                        break  # break out of loop if no branches are supposed to be made.
            modified_spaces.append(
                DeltaSpace(  # use tuples for efficient storage... more efficient that way.
                    input_space=prev_space,
                    output_space=tuple(submitted_spaces),
                    cell_deltas=tuple(submitted_cell_deltas)
                )
            )

        self = top_self  # make sure we are referring to the top of the chain version of "self"
        # ensure the lifespan is enforced
        self.lifespan -= 1  # will not affect infinity if so set
        if self.lifespan == 0 and modified_spaces:
            self.disabled = True
        self.on_applied.emit(self, modified_spaces)
        return modified_spaces


class SubstitutionRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: Sequence[Cell]) -> DeltaCell:
        return space.substitute(selector, deepcopy(target))


class InsertionRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: Sequence[Cell]) -> DeltaCell:
        return space.insert(selector[0], deepcopy(target))


class OverwriteRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: Sequence[Cell]) -> DeltaCell:
        return space.overwrite(selector[0], deepcopy(target))


class DeletionRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: None) -> DeltaCell:
        return space.delete(selector)


class ShiftingRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: int) -> DeltaCell:
        return space.shift(selector, k=target)


class ReverseRule(BaseRule):
    def _call_space_modifier(self, space: SpaceState, selector: tuple[int, int], target: None) -> DeltaCell:
        return space.reverse(selector)


if __name__ == "__main__":
    pass
