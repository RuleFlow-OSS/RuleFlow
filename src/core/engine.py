from typing import Any, Sequence, MutableSequence, NamedTuple, Iterator, cast, Self, Hashable, Protocol, runtime_checkable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from core.signals import Signal
from copy import copy


@runtime_checkable  # this lets isinstance work with implemented Cells. It should be noted, however, that type checks are not performed on attributes or methods, only that the structure exists.
class Cell(Protocol):
    """A single unit within a universe (a.k.a. Quanta).
    A cell is analogous to a discrete spacial-unit and quanta is the matter that fills up that unit of space.
    It is at this smallest unit of space that we care about causality.

    Note that the `destroyed_at` attribute was deprecated due to adding memory that is rarely used,
    and is harder to track under a data-oriented approach (problems with lists of lists in numpy for instance)."""

    @property
    def quanta(self) -> int:
        """The semantic value of the cell."""
        ...

    @quanta.setter
    def quanta(self, value: int) -> None:
        """The semantic value of the cell."""
        ...

    @property
    def created_at(self) -> int:
        """Getter for `created_at` value (index of the event the cell was created at)."""
        ...

    @created_at.setter
    def created_at(self, value: int) -> None:
        """Setter for `created_at` value."""
        ...

    @property
    def id(self) -> int:
        """Getter for the unique `id` of the cell."""
        ...

    @id.setter
    def id(self, value: int) -> None:
        """Setter for the `id` value."""
        ...



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
    def __str__(self) -> str:
        """String representation of SpaceState"""

    @abstractmethod
    def __repr__(self) -> str:
        """Object representation of SpaceState"""

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
    def __hash__(self) -> int:
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
        """Returns all the cells that live in the SpaceState... regardless of the space's topology.
        This is useful for modifying all the cells in the SpaceState."""

    @abstractmethod
    def get_cell(self) -> Cell:
        """Returns all the cells that live in the SpaceState... regardless of the space's topology.
        This is useful for modifying all the cells in the SpaceState."""

    @abstractmethod
    def find(self, subspace: Cell | Sequence[Cell] | Any) -> Iterator[int | Any]:
        """Find the `instances` number of occurrences of subspaces in the space (in any order desired) and return a
        sequence of index positions or more complex positions. An empty set is returned if no matches are found.
        If `instances` is -1, all subspaces should be matched.
        Note that `instances` are useful for creating multi-way systems for example."""


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
        self.group: tuple[Hashable, ...] = (0,)  # group together rules this way. Can be part of multiple groups
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

        Rule is responsible for taking all current states to provide maximum flexibility (so different rules can have different behavior: sessies + messies) (Source: TRUST ME BRO!!! I doubted my past self on this and then wasted a bunch of time... just keep it as-is you crazy future self!)
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
            active: bool = any(group_management.setdefault(g, True) for g in rule.group)
            if not active and not rule.always_apply:
                continue
            rule_matches: Sequence[RuleMatch] = rule.match(to_spaces)
            if rule_matches:  # if there are any rule matches.
                space_deltas: DeltaSpaces = DeltaSpaces(rule.apply(rule_matches), rule)
                if space_deltas:  # to be robust in case a complex rule still fails (even though input matches were found we can't guarantee that it will always work)
                    applied_rules.append(space_deltas)
                    if rule.group_break:
                        for g in rule.group:
                            group_management[g] = False
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
    cell_deltas: Sequence[DeltaCell]  # should be aligned with output_space array (so branches align)

    def __bool__(self) -> bool:
        return any(self.output_space) or any(self.cell_deltas)  # we check both to be as robust as possible... what if a rule does not return delta cells due to modifying but not adding or deleting?


class DeltaSpaces(NamedTuple):  # returned by RuleSet.apply() in a Sequence[DeltaSpaces]
    """All delta spaces that happened under a given rule."""
    space_deltas: Sequence[DeltaSpace]
    rule: Rule | None

    def __bool__(self) -> bool:
        return any(self.space_deltas)  # if any changes were recorded.

# TODO: maybe cache the properties?
@dataclass(slots=True)
class Event:
    time: int  # also known as time - should be sequential and unique to every event
    space_deltas: list[DeltaSpaces]  # all space deltas (organized by the rules they were applied under)

    # metadata
    inert: bool = False  # if true, the new event caused no changes to the system.
    weight: int | float = 1  # could be used for weighted causality tracking. (think of it as a time multiplier/dilator)
    causal_distance_to_creation: int = 0  # minimum distance (min number of nodes) to the creation event node.

    @property
    def affected_cells(self) -> Iterator[DeltaCell]:
        """Returns all cell deltas"""
        for r in self.space_deltas:
            for space_delta in r.space_deltas:
                for cell_delta in space_delta.cell_deltas:
                    if cell_delta:
                        yield cell_delta

    @property
    def causally_connected_events(self) -> Iterator[int]:
        """Returns events (stored as indices) whose created cells were destroyed by this event"""
        for delta in self.affected_cells:
            for cell in delta.destroyed_cells:
                yield cell.created_at

    @property
    def spaces(self) -> Iterator[SpaceState]:
        """Returns all newly created spaces"""
        for r in self.space_deltas:
            for space_delta in r.space_deltas:
                for space in space_delta.output_space:
                    if space is not None:
                        yield space

    @property
    def spaces_with_metadata(self) -> Iterator[tuple[DeltaSpaces, DeltaSpace, SpaceState]]:
        """Returns all newly created spaces along with their metadata (in the parent structure)"""
        for r in self.space_deltas:
            for space_delta in r.space_deltas:
                for space in space_delta.output_space:
                    if space is not None:
                        yield r, space_delta, space

    def __str__(self):
        return '[' + ', '.join(str(space) for space in self.spaces) + ']'  # TODO remove this to a dedicated printer


class Flow:
    """The base class for a rule flow, additional behavior should be implemented by subclassing this class."""

    def __init__(self):
        self.ruleset: RuleSet = RuleSet([])  # can be changed at any time to provide a new set of rules.
        self.events: list[Event] = []  # defaults to empty... but nothing will work properly

        # progress tracking attributes
        self.n_step_progress: float = 0  # percentage of steps run by some_method_n().

        # Signals (can be used to live update analysis objects like the causal graph)
        self.on_evolved_step: Signal = Signal()
        self.on_evolved_n: Signal[int] = Signal()  # after all evolves
        self.on_undone_step: Signal = Signal()
        self.on_undone_n: Signal[int] = Signal()  # after all undo's
        self.on_clear: Signal = Signal()
        self.on_ruleset_set: Signal = Signal()

        # hidden properties
        self._dirty_thread: bool = False  # used safely to interrupt a method running inside a thread.

    def set_ruleset(self, ruleset: RuleSet) -> None:
        """Used to set the rule set"""
        self.ruleset: RuleSet = ruleset
        self.on_ruleset_set.emit()

    def set_initial_space(self, initial_space: Sequence[SpaceState]) -> None:
        """Used to set the initial space"""
        if not self.events:
            self.events.append(cast(Event, cast(object, 0)))
        self.events[0] = Event(0, [DeltaSpaces(tuple((DeltaSpace(i, (i,), (DeltaCell((), ()),)) for i in initial_space)), None)])  # initial output space must be `i` as well so that next evolve() works.
        for i in initial_space:
            for cell in i.get_all_cells():
                cell.created_at = 0

    def clear_evolution(self) -> None:
        """Clear the evolution."""
        del self.events[1:]
        self.on_clear.emit()

    @property
    def current_event(self) -> Event:
        return self.events[-1]

    @property
    def current_event_idx(self) -> int:
        return len(self.events) - 1

    def _evolve(self) -> None:
        """ Evolve the system by one step.

        This can be reimplemented by subclasses to modify behavior. As it stands, it does the following:
        - apply the rules to the current space states using RuleSet.apply()
        - if a rule was successfully applied, create a new event and increment the time ``step``
        - Update event and cell metadata (important for tracking causality)
            - set the applied rules (the applied rules are associated with the space states they modified)
            - extract all the modified space states from the applied rules and add them to the space states of the Event.
        """
        applied_rules: list[DeltaSpaces] = self.ruleset.apply(to_spaces=tuple(self.current_event.spaces))
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

        # process causal distance to creation
        min_prev: int = min((self.events[e_idx].causal_distance_to_creation
                             for e_idx in self.current_event.causally_connected_events),
                            default=-1)
        self.current_event.causal_distance_to_creation = min_prev + 1

        # emit any signals
        self.on_evolved_step.emit()

    def evolve(self, n_steps: int, break_when_inert: bool = False) -> None:
        """Evolve the system n steps."""
        i: int = 0
        self._dirty_thread = False  # must reset
        while i < n_steps:
            # print(str(next(self.current_event.spaces).cells.search_buffer).replace('A', '\x1b[1;41m A \x1b[0m').replace('B', '\x1b[1;42m B \x1b[0m'))  # if we want to see how the buffer changes.
            self.n_step_progress = (i + 1) / n_steps
            i += 1
            self._evolve()
            if break_when_inert and self.current_event.inert:
                break
            if self._dirty_thread:
                break

        # emit any signals
        self.on_evolved_n.emit(n_steps)

    def _regress(self) -> None:
        """Revert to the last event..."""
        for ar in self.current_event.space_deltas:
            for sd in ar.space_deltas:
                for dc in sd.cell_deltas:
                    for cell in dc.destroyed_cells:
                        cell.destroyed_at = tuple(i for i in cell.destroyed_at if i != self.current_event_idx)
        self.events.pop()

        # emit any signals
        self.on_undone_step.emit()

    def regress(self, n_steps: int) -> None:
        self._dirty_thread = False  # must reset
        for _ in range(n_steps):
            self.n_step_progress = (_ + 1) / n_steps
            self._regress()
            if self._dirty_thread:
                break

        self.on_undone_n.emit(n_steps)

    def stop_thread(self):
        """Used to safely interrupt any long-running methods in a thread."""
        self._dirty_thread = True

    def __str__(self) -> str:
        return '\n'.join(str(e) for e in self.events)


if __name__ == '__main__':
    pass
