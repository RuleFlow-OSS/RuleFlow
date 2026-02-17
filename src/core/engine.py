from typing import Any, Sequence, MutableSequence, NamedTuple, Iterator
from abc import ABC, abstractmethod
from dataclasses import dataclass
from copy import copy
from core.signals import Signal


# ==== engine ====
@dataclass(slots=True)  # we use slots to get C-like mutable struct behavior (NamedTuple is similar but immutable)
class Cell:
    """A single (technically) mutable unit within a universe/string (a.k.a. Quanta). However, it is usually treated as immutable using copy() and hash().
    A cell is analogous to a discrete spacial-unit and quanta is the matter that fills up that unit of space.
    It is at this smallest unit of space that we care about causality.

    Policies:
    - The Cell class should not contain any fields other than the quanta and the metadata. This is so copies can be made easily.

    Future Considerations:
    - Add additional metadata/tags fields.
    """
    quanta: Any

    # NOTE: the metadata is the ONLY thing that makes cells differentiable (other than quanta of course)
    # Metadata regarding the creation and destruction of the cell... stored as indices to the events array.
    created_at: int = 0  # this is the ONLY piece important metadata needed for a causality graph (can only be created one, so one event index)
    destroyed_at: tuple[int, ...] = ()  # OPTIONAL metadata useful for analysis. Is an array of event indices (multiple indices for multiway systems)

    def __str__(self):
        """String representation of quanta"""
        return str(self.quanta)

    def __repr__(self):
        return repr(self.quanta)

    def __eq__(self, other: Cell):
        """Semantic equality (use is for true equality)"""
        return self.quanta == other.quanta

    # noinspection PyDunderSlots,PyUnresolvedReferences
    def __copy__(self) -> Cell:
        n: Cell = object.__new__(self.__class__)
        n.quanta = self.quanta
        n.created_at = self.created_at
        n.destroyed_at = self.destroyed_at
        return n

    def __deepcopy__(self, memo) -> Cell:
        return self.__copy__()  # force normal copy() behavior

    def __hash__(self):  # implemented to make Cell hashable (so can be used as keys in dict for instance)
        return hash(self.quanta)


class SpaceState(ABC):
    """Mutable container made up of `Cells` (a.k.a. Universe State of Space).

    Policies:
    - Should NOT be used as a simple container for Cells (in a replacement rule for instance), it should only be used for actual space states in events/time. Any other container should be in the form Sequence[Cell].
    - All modifier methods must make sure to create new cells or cell copies if causality is to be tracked properly using the DeltaSets.
    - All modifier methods (that create/destroy cells) should return DeltaCellSet containing the destroyed and created cells.
    - All official SpaceStates must be created in this engine.py file. If one wants to create a 4D SpaceState, for instance, they must inherit from this, implement the methods, etc.
    - All SpaceStates that inherit from this class must implement the modifier methods. If `find`, `len`, etc. are not sufficient helpers, additional helpers may be created here (if they are general enough), or in the subclasses ideally.
    """

    @abstractmethod
    def __str__(self):
        """String representation of SpaceState"""

    @abstractmethod
    def __repr__(self):
        """Repr String representation of SpaceState"""

    @abstractmethod
    def __eq__(self, other: SpaceState) -> bool:
        """Semantic equality (use `is` for true equality)"""

    @abstractmethod
    def __len__(self) -> int | Any:
        """Should return the *size* of a container... whatever that may mean for N^1 or N^2 or N^3 spaces."""

    @abstractmethod
    def __bool__(self) -> bool:
        """Should return the bool state of the space (has any contents)."""

    @abstractmethod
    def __hash__(self):
        """Should make the SpaceState hashable so that it can be stored in a hash table."""

    @abstractmethod
    def __copy__(self) -> SpaceState | Any:
        """Copies the SpaceState (self), but does not copy the cells (internal fields) themselves
        (it only retains references to them). It is a shallow copy.
        """

    @abstractmethod
    def __getitem__(self, item: int | slice) -> Cell | Sequence[Cell] | Any:
        """Enables getting subspaces with slicing: space[0][1] of an N^2 space for instance."""

    @abstractmethod
    def get_all_cells(self) -> Sequence[Cell] | Iterator[Cell]:
        """Returns all the cells that live in the SpaceState... regardless of the spaces dimensions.
        This is useful for modifying all the cells in the SpaceState."""

    @abstractmethod
    def find(self, subspace: Cell | Sequence[Cell] | Any) -> Iterator[int | Any]:
        """Find the `instances` number of occurrences of subspaces in the space (in any order desired) and return a
        sequence of index positions or more complex positions. An empty set is returned if no matches are found.
        If `instances` is -1, all subspaces should be matched.
        Note that `instances` are useful for creating multi-way systems for example."""


class SpaceState1D(SpaceState):
    """A SpaceState for a single dimensions (string) of space units (cells).

    If sparse is set to True, a persistent data structure is used to share pointers between changes (can save a lot of memory)."""
    __slots__ = 'cells',

    def __init__(self, cells: MutableSequence[Cell]) -> None:
        self.cells: MutableSequence[Cell] = cells

    def __str__(self):
        return ''.join((str(c) for c in self.cells))

    def __repr__(self):
        return str(self)

    def __eq__(self, other: SpaceState1D) -> bool:
        for sc, oc in zip(self.cells, other.cells):
            if sc.quanta != oc.quanta:
                return False
        return True

    def __len__(self) -> int:
        return len(self.cells)

    def __bool__(self) -> bool:
        return bool(self.cells)

    def __hash__(self):
        return hash(tuple(self.cells))

    def __copy__(self) -> SpaceState1D:
        new_space: SpaceState1D = object.__new__(self.__class__)  # create new object without using init
        new_space.cells = copy(self.cells)
        return new_space

    def __getitem__(self, item: int | slice) -> Cell | Sequence[Cell]:
        return self.cells[item]

    def get_all_cells(self) -> Sequence[Cell]:
        return self.cells

    def find(self, subspace: Sequence[Cell]) -> Iterator[tuple[int, int]]:
        subspace_len: int = len(subspace)
        for i in range(len(self.cells) - subspace_len + 1):  # we use left-to-right search
            if all(self.cells[i + j] == subspace[j] for j in range(subspace_len) if subspace[j].quanta != '.'):
                yield i, i + subspace_len

    # ==== Custom Modifiers ====
    def substitute(self, selector: tuple[int, int], new: Sequence[Cell]) -> DeltaCell:
        start, end = selector
        destroyed: tuple[Cell, ...] = tuple(self.cells[start:end])
        self.cells[start:end] = new
        return DeltaCell(destroyed, new)

    def insert(self, selector: int, new: Sequence[Cell]) -> DeltaCell:
        if selector < 0:
            selector = len(self.cells) + selector + 1
        self.cells[selector:selector] = new
        return DeltaCell((), new)

    def overwrite(self, selector: int, new: Sequence[Cell]) -> DeltaCell:
        destroyed: tuple[Cell, ...] = ()
        new_: tuple[Cell, ...] = ()  # only here due to "_" being a cursor jump/skip operator
        if selector < 0:
            selector = len(self.cells) + selector
        for i in range(len(new)):
            idx = selector + i
            new_char: Cell = new[i]
            if new_char.quanta == '_':  # skip these
                continue
            try:
                destroyed += (self.cells[idx],)
                self.cells[idx] = new_char
            except IndexError:
                self.cells.append(new_char)
            new_ += (new_char,)
        return DeltaCell(destroyed, new_)

    def delete(self, selector: tuple[int, int]) -> DeltaCell:
        start, end = selector
        destroyed: tuple[Cell, ...] = tuple(self.cells[start:end])
        self.cells[start:end] = ()
        return DeltaCell(destroyed, ())

    def shift(self, selector: tuple[int, int], k: int) -> DeltaCell:
        start, end = selector
        if end < 0: end = len(self.cells) + end
        if start < 0: start = len(self.cells) + start
        if k == 0:
            pass
        elif k < 0:
            k = abs(k)
            self.cells[end:end] = self.cells[start - k:start]  # insert "before" to "after"
            self.cells[start - k:start] = ()  # delete before
        else:
            temp = self.cells[end:end + k]  # delete "after" but remember it
            self.cells[end:end + k] = ()
            self.cells[start:start] = temp  # insert "after" to "before"
        return DeltaCell((), ())

    def swap(self, selector1: tuple[int, int], selector2: tuple[int, int]) -> DeltaCell:
        start1, end1 = selector1
        if end1 < 0: end1 = len(self.cells) + end1
        if start1 < 0: start1 = len(self.cells) + start1
        start2, end2 = selector2
        if end2 < 0: end2 = len(self.cells) + end2
        if start2 < 0: start2 = len(self.cells) + start2
        if (start1 < start2 < end1 or start1 < end2 < end1
                or start2 < start1 < end2 or start2 < end1 < end2):  # we do additional checks to ensure that huge slices are still caught.
            raise IndexError('The selector indices cannot overlap!')
        if start2 < start1:
            start1, start2 = start2, start1
            end1, end2 = end2, end1
        temp1 = self.cells[start1:end1]
        temp2 = self.cells[start2:end2]
        self.cells[start2:end2] = temp1
        self.cells[start1:end1] = temp2
        return DeltaCell((), ())

    def reverse(self, selector: tuple[int, int]) -> DeltaCell:
        start, end = selector
        self.cells[start:end] = self.cells[start:end][::-1]
        return DeltaCell((), ())


class SpaceState2D(SpaceState):
    """It is here that we implement the 2D SpaceState. Just a placeholder for now."""
    pass


class SpaceStateGraph(SpaceState):
    """It is here that we implement the graph SpaceState. Just a placeholder for now."""
    pass


class RuleMatch(NamedTuple):
    """An object that represents a rule match. This is returned by Rule.match() and passed to Rule.apply()."""
    space: SpaceState
    matches: Sequence[tuple[int, int]] | Any  # Any is to support higher dimension matches.
    conflicts: set[int]  # conflicting matches (idx of the match) that must be resolved.
    metadata: Any = None  # optional metadata


class Rule(ABC):
    def __init__(self):
        """Should take arguments that define the rule behavior. For instance, ``SubstitutionRule(match: string, replace: string)`` should be for a rule that finds a matching substring and replaces it.
        ``InsertionRule(insert: string, at_idx: string)`` should be a rule that inserts a string at the specified index. Whatever the init arguments are, they must be created as fields internally in an elegant format.

        The Rule should be responsible for duplicating (or not) the SpaceState(s) when applying itself. This way,
        multi-way systems are supported because the Rule can apply multiple different modifications to multiple
        different SpaceStates if necessary.

        Note that all the code is assuming that multi-way systems take place for multiple modifications. However, if we want to modify a SpaceState, without creating branches, we must do that in the Rule itself (i.e. having entire "rulesets" within rules).
        """
        # metadata
        self.id: str = ''  # could be used to filter rules.

        # Flags (these are only those which modify default RuleSet behavior)
        self.disabled: bool = False  # if the rule is disabled (dead)
        self.group: int | str = 0  # group together rules this way.
        self.group_break: bool = True  # break out of the group upon successful application of rule.
        self.always_apply: bool = False  # always apply this rule no matter what (disregards grouping)
        # NOTE: any and all additional flags that modify internal rule behavior MUST (for the sake of clarity) be in the implementation of the rule.

    @abstractmethod
    def match(self, spaces: Sequence[SpaceState]) -> Sequence[RuleMatch]:
        pass

    @abstractmethod
    def apply(self, rule_matches: Sequence[RuleMatch]) -> Sequence[DeltaSpace]:
        """Applies the rule to the given ``SpaceState(s)``. Modified SpaceStates are returned.
        Important for implementation: *new/copied* SpaceState(s) must be created, modified, and returned.

        Rule is responsible for taking all current states to provide maximum flexibility (so different rules can have different behavior: sessies + messies) (TRUST ME!!! I doubted my past self on this and then wasted a bunch of time... just keep it as-is you crazy future self!)
        """
        pass


class RuleSet:
    """This contains the Rules that can be applied. Additional, more complex, behavior can be implemented by subclassing it.

    Note that all the code is engineered around assuming multi-way systems for more than one rule being applied.
    """

    def __init__(self, rules: list[Rule]):
        """This should be implemented by subclasses.
        This should ideally accept a list of Rules either as objects or as strings that should then be parsed into their corresponding rules. The rules should be stored in array."""
        self.rules: list[Rule] = rules

    def __str__(self) -> str:
        return str(self.rules)

    def __repr__(self) -> str:
        return str(self)

    def apply(self, to_spaces: Sequence[SpaceState]) -> list[DeltaSpaces]:
        """Applies the Rules to the given spaces, and returns a sequence of the DeltaSpaceSet."""
        group_management: dict = {
            # group IDs go here along with whether they are active - id: bool
        }
        applied_rules: list[DeltaSpaces] = []
        for rule in self.rules:
            if rule.disabled:
                continue
            active: bool = group_management.setdefault(rule.group, True)
            if not active and not rule.always_apply:
                continue
            rule_matches: Sequence[RuleMatch] = rule.match(to_spaces)
            if rule_matches:  # if there are any rule matches.
                space_deltas: DeltaSpaces = DeltaSpaces(rule.apply(rule_matches), rule)
                if space_deltas:  # to be robust in case a complex rule still fails (even though input matches were found we can't guarantee that it will always work)
                    applied_rules.append(space_deltas)
                    if rule.group_break: group_management[rule.group] = False
        return applied_rules


class DeltaCell(NamedTuple):  # the cells that were created and destroyed by some SpaceState.modifier() method.
    destroyed_cells: Sequence[Cell]
    new_cells: Sequence[Cell]

    def __bool__(self) -> bool:
        return bool(self.destroyed_cells) or bool(self.new_cells)  # if any changes occurred, return true.


class DeltaSpace(NamedTuple):  # returned by Rule.apply() in a Sequence[DeltaSpace]
    """Single application of a rule within Rule.apply()."""
    input_space: SpaceState  # we always have this filled so that we know what spaces had what changes (if any) made
    output_space: Sequence[SpaceState | None]  # can include many children branches
    cell_deltas: Sequence[DeltaCell]  # should be aligned with output_space array

    def __bool__(self) -> bool:
        return any(self.output_space) or any(self.cell_deltas)  # we check both to be as robust as possible... what if a rule does not return delta cells due to modifying but not adding or deleting?


class DeltaSpaces(NamedTuple):  # returned by RuleSet.apply() in a Sequence[DeltaSpaces]
    """All delta spaces that happened under a given rule."""
    space_deltas: Sequence[DeltaSpace]
    rule: Rule | None

    def __bool__(self) -> bool:
        return any(self.space_deltas)  # if any changes were recorded.


@dataclass(slots=True)
class Event:
    time: int  # also known as time - should be unique to every event
    space_deltas: list[DeltaSpaces]  # all space deltas (organized by the rules they were applied under)

    # metadata
    inert: bool = False  # if true, the new event caused no changes to the system.
    weight: int | float = 1  # could be used for weighted causality tracking. (think of it as a time multiplier/dilator)
    causal_distance_to_creation: int = 0  # minimum distance (min number of nodes) to the creation event node.

    @property  # maybe cache this?
    def affected_cells(self) -> Iterator[DeltaCell]:
        """Returns all cell deltas"""
        for r in self.space_deltas:
            for space_delta in r.space_deltas:
                for cell_delta in space_delta.cell_deltas:
                    if cell_delta:
                        yield cell_delta

    @property  # maybe cache this?
    def causally_connected_events(self) -> Iterator[int]:
        """Returns events (stored as indices) whose created cells were destroyed by this event"""
        for delta in self.affected_cells:
            for cell in delta.destroyed_cells:
                yield cell.created_at

    @property  # maybe cache this?
    def spaces(self) -> Iterator[SpaceState]:
        """Returns all newly created spaces"""
        for r in self.space_deltas:
            for space_delta in r.space_deltas:
                for space in space_delta.output_space:
                    if space is not None:
                        yield space

    def __str__(self):
        return '[' + ', '.join(str(space) for space in self.spaces) + ']'  # TODO remove this to a dedication printer


# We use these noinspections because of stupid PyCharm bug regarding slots and dataclasses that has not been fixed...
# noinspection PyDunderSlots,PyUnresolvedReferences
class Flow:
    """The base class for a rule flow, additional behavior should be implemented by subclassing this class."""

    # Signals (can be used to live update analysis objects like the causal graph)
    on_evolve: Signal = Signal()
    on_undo: Signal = Signal()

    def __init__(self):
        self.rule_set: RuleSet = RuleSet([])  # can be changed at any time to provide a new set of rules.
        self.events: list[Event] = []  # defaults to empty... but nothing will work properly
        self.event_index_offset: int = 0

    def set_ruleset(self, ruleset: RuleSet) -> None:
        """Used to set the rule set"""
        self.rule_set: RuleSet = ruleset

    def set_initial_space(self, initial_space: Sequence[SpaceState]) -> None:
        """Used to set the initial space"""
        self.events.insert(
            0,
            Event(0, [DeltaSpaces(tuple((DeltaSpace(i, (i,), (DeltaCell((), ()),)) for i in initial_space)), None)])  # initial output space must be i as well so that next evolve() works.
        )
        for i in initial_space:
            for cell in i.get_all_cells():
                cell.created_at = 0

    def clear_evolution(self) -> None:
        """Clear the evolution."""
        del self.events[1:]

    @property
    def current_event(self) -> Event:
        try:
            return self.events[self.current_event_idx]
        except IndexError:  # when the offset is too large or no events exist
            if len(self.events) == 0:
                raise IndexError('No events exist')
            self.set_event_offset(0)  # fix offset
            return self.current_event

    @property
    def current_event_idx(self) -> int:
        return len(self.events) - 1 - self.event_index_offset

    def set_event_offset(self, offset: int, from_init: bool = False) -> None:
        """Shift the current index in the flow of events"""
        if offset < 0:
            raise ValueError('Offset cannot be negative')
        if from_init:
            offset = len(self.events) - 1 - offset
        self.event_index_offset = offset

    def evolve(self) -> None:
        """ Evolve the system by one step.

        This can be reimplemented by subclasses to modify behavior. As it stands, it does the following:
        - apply the rules to the current space states using RuleSet.apply()
        - if a rule was successfully applied, create a new event and increment the time ``step``
        - Update event and cell metadata (important for tracking causality)
            - set the applied rules (the applied rules are associated with the space states they modified)
            - extract all the modified space states from the applied rules and add them to the space states of the Event.
        """
        applied_rules: list[DeltaSpaces] = self.rule_set.apply(to_spaces=tuple(self.current_event.spaces))
        if not any(applied_rules):  # if no rules made any modifications to the spaces
            self.current_event.inert = True
            return

        # Create a new event and process it
        self.events.append(
            Event(self.current_event.time + 1, space_deltas=applied_rules)  # create a new event
        )

        # process causality
        current_event_idx: int = self.current_event_idx
        for ar in applied_rules:
            for sd in ar.space_deltas:
                for dc in sd.cell_deltas:
                    for cell in dc.new_cells:
                        cell.created_at = current_event_idx
                    for cell in dc.destroyed_cells:
                        cell.destroyed_at += (current_event_idx,)  # first one, of course, will be the main lineage

        # process causal distance to creation
        min_prev: int = min((self.events[e_idx].causal_distance_to_creation for e_idx in self.current_event.causally_connected_events), default=-1)
        self.current_event.causal_distance_to_creation = min_prev + 1

        # emit any signals
        self.on_evolve.emit(self)

    def evolve_n(self, n_steps: int, break_when_inert: bool = False) -> None:
        """Evolve the system n steps."""
        while n_steps > 0:
            # print(str(next(self.current_event.spaces).cells.search_buffer).replace('A', '\x1b[1;41m A \x1b[0m').replace('B', '\x1b[1;42m B \x1b[0m'))  # if we want to see how the buffer changes.
            self.evolve()
            n_steps -= 1
            if break_when_inert and self.current_event.inert:
                break

    def undo(self) -> None:
        """undo the last event..."""
        if self.current_event_idx == 0:
            return
        for ar in self.current_event.space_deltas:
            for sd in ar.space_deltas:
                for dc in sd.cell_deltas:
                    for cell in dc.destroyed_cells:
                        cell.destroyed_at = tuple(i for i in cell.destroyed_at if i != self.current_event_idx)
                    if self.event_index_offset:  # shift the created_at up if we are in the middle of an evolution
                        for cell in dc.new_cells:
                            cell.created_at = current_event_idx + 1
        self.events.pop(self.current_event_idx)

        # emit any signals
        self.on_undo.emit(self)

    def undo_n(self, n_steps: int) -> None:
        for _ in range(n_steps):
            self.undo()

    def __str__(self) -> str:
        return '\n'.join(str(e) for e in self.events)


if __name__ == '__main__':
    pass
