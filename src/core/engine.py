"""core.engine
This implements the necessary abstraction layer and protocols as well as logic flow necessary to
evolve systems that can be causally tracked.

All printer `__str__()` implementations are primarily for debugging purposes; rendering implementation are in
dedicated modules.
"""
from typing import Any, NamedTuple, cast, Protocol, runtime_checkable
from collections.abc import Sequence, Iterator, Hashable
from abc import ABC, abstractmethod
from dataclasses import dataclass
from core.signals import Signal


@runtime_checkable  # this lets isinstance work with implemented Cells. It should be noted, however, that type checks are not performed on attributes or methods, only that the structure exists.
class Cell(Protocol):
    """A single unit within a universe (a.k.a. Quanta).
    A cell is analogous to a discrete/atomic spacial-unit and quanta is the matter that fills up that unit of space.
    It is at this smallest unit of space that we care about causality. There are two ways that this protocol may be
    implemented: (1) we store the attributes on the Cell object, or (2) we only store an address to those values in
    the topology. The second way is preferable, but one must be careful to only make references to that which they
    know won't change unexpectedly. The second way has the added benefit of additional information attached to each
    cell, namely its location. This is significant because each Cell is therefore treated as a constant location
    in space, regardless of what quanta happens to occupy it. An implementation of method (2) can be found in the
    CellVector implementation (topologies.vector).

    Note that the `destroyed_at` attribute was deprecated due to adding memory that is rarely used, and is harder to
    track (due to multi-ways) under a data-oriented approach (problems with lists of lists in numpy for instance).
    Flow.find_cell_lifespan is used instead and provides much better support for multiways.

    Note that NamedTuples satisfy this protocol even though the setter methods throw errors."""
    quanta: int
    generation: int
    id: int


@runtime_checkable
class Topology(Protocol):
    """The data structure implementation that manages the persistence/lower level modification of a state.
    All topology implementations must follow this protocol.
    It is also responsible for causality tracking via next_gen."""

    as_cells: Iterator[Cell]
    """Get (usually as a property) all cells contained in this topology."""

    def get_cell(self, index: Any) -> Cell:
        """Get a specific cell within this topology."""

    def get_cells(self, index: Any) -> Iterator[Cell]:
        """Get a range of Cells within this topology."""

    def next_gen(self) -> Topology:
        """Return a copy of the current topology but update any necessary attributes such that causality is tracked."""


class SpaceState(ABC):
    """Topology wrapper that offers modifiers for the state (a.k.a. Universe State of Space).

    Policies:
    - Should NOT be used as a simple container for Cells, it should only be a wrapper around an underling topology that provides needed behavior for modifications and analysis.
    - All modifier methods (that create/destroy vec) should return a DeltaSet containing the destroyed and created vec.
    - All SpaceStates that inherit from this class must implement the modifier methods. Additional topology specific methods must be accessible via self.topology.
    """

    @abstractmethod
    def __str__(self) -> str:
        """String representation of SpaceState"""

    @abstractmethod
    def __repr__(self) -> str:
        """Object representation of SpaceState"""

    @abstractmethod
    def next_gen(self) -> SpaceState:
        """This is to be used as the method for creating the next generation."""

    @property
    @abstractmethod
    def topology(self) -> Topology:
        """Returns the topology data structure (i.e. CellVector, HyperGraph, etc.)"""


class RuleMatch(NamedTuple):
    """An object that represents a rule match. This is returned by Rule.match() and passed to Rule.apply()."""
    space: SpaceState
    matches: Sequence[tuple[int, int]] | Any  # Any is to support higher dimension matches.
    conflicts: set[int] | frozenset[int]  # conflicting matches (idx of the match) that must be resolved.
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

    def apply(self, to_spaces: Sequence[SpaceState]) -> list[DeltaSpace]:
        """Applies the Rules to the given spaces, and returns a sequence of DeltaSpace."""
        group_management: dict = {
            # group IDs go here along with whether they are active - id: bool
        }
        space_deltas: list[DeltaSpace] = []
        for rule in self.rules:
            if rule.disabled:
                continue
            active: bool = any(group_management.setdefault(g, True) for g in rule.group)
            if not active and not rule.always_apply:
                continue
            rule_matches: Sequence[RuleMatch] = rule.match(to_spaces)
            if rule_matches:  # if there are any rule matches.
                _space_deltas: Sequence[DeltaSpace] = rule.apply(rule_matches)
                if any(_space_deltas):  # to be robust in case a complex rule still fails (even though input matches were found we can't guarantee that it will always work)
                    space_deltas.extend(_space_deltas)
                    if rule.group_break:
                        for g in rule.group:
                            group_management[g] = False
        return space_deltas


class DeltaCell(NamedTuple):
    """The cells that were created and destroyed by some SpaceState.modifier() method."""
    destroyed_cells: Sequence[Cell]
    new_cells: Sequence[Cell]

    def __bool__(self) -> bool:
        return bool(self.destroyed_cells) or bool(self.new_cells)  # if any changes occurred, return true.


class DeltaSpace:  # returned by Rule.apply() in a Sequence[DeltaSpace]
    """Single application of a rule within Rule.apply()."""
    __slots__ = ('input_space', 'output_space', 'cell_deltas', 'rule', 'parent_delta')

    def __init__(self, input_space: SpaceState,
                 output_space: Sequence[SpaceState],
                 cell_deltas: Sequence[DeltaCell],
                 rule: Rule | None,
                 parent_delta: DeltaSpace | None = None) -> None:
        self.input_space: SpaceState = input_space
        self.output_space: Sequence[SpaceState] = output_space
        self.cell_deltas: Sequence[DeltaCell] = cell_deltas  # should be aligned with output_space array
        self.rule: Rule | None = rule
        self.parent_delta: DeltaSpace = self if parent_delta is None else parent_delta  # this is so that we can traverse the multiway tree and is why this is a slots class rather than a NamedTuple which has problems with mutable fields that are weak referenced.

    def __bool__(self) -> bool:
        return any(self.output_space) or any(self.cell_deltas)  # we check both to be as robust as possible... what if a rule does not return delta vec due to modifying but not adding or deleting?


# TODO: maybe cache the properties?
@dataclass(slots=True)
class Event:
    time: int  # also known as time - should be sequential and unique to every event
    space_deltas: list[DeltaSpace]  # all space deltas (organized by the rules they were applied under)

    # metadata
    inert: bool = False  # if true, the new event caused no changes to the system.
    weight: int | float = 1  # could be used for weighted causality tracking. (think of it as a time multiplier/dilator)
    causal_distance_to_creation: int = 0  # minimum distance (min number of nodes) to the creation event node.

    @property
    def affected_cells(self) -> Iterator[DeltaCell]:
        """Returns all cell deltas"""
        for space_delta in self.space_deltas:
            for cell_delta in space_delta.cell_deltas:
                if cell_delta:
                    yield cell_delta

    @property
    def causally_connected_events(self) -> Iterator[int]:
        """Returns events (stored as indices) whose created vec were destroyed by this event"""
        for delta in self.affected_cells:
            for cell in delta.destroyed_cells:
                yield int(cell.generation)  # convert to normal int in case, for instance, it is a numpy int.

    @property
    def spaces(self) -> Iterator[SpaceState]:
        """Returns all newly created spaces"""
        for space_delta in self.space_deltas:
            for space in space_delta.output_space:
                yield space

    @property
    def spaces_with_deltas(self) -> Iterator[tuple[DeltaSpace, DeltaCell, SpaceState]]:
        """Returns all newly created spaces along with their metadata (in the parent structure)"""
        for space_delta in self.space_deltas:
            for cell_delta, space in zip(space_delta.cell_deltas, space_delta.output_space):
                yield space_delta, cell_delta, space

    def __str__(self):
        return '[' + ', '.join(str(space) for space in self.spaces) + ']'


class Coordinate(NamedTuple):
    """A unique branch (useful for multi-ways)"""
    event_idx: int
    space_idx: int

    def __str__(self) -> str:
        return f'({self.event_idx}, {self.space_idx})'


class Flow:
    """The base class for a rule flow, additional behavior should be implemented by subclassing this class."""

    def __init__(self):
        self.ruleset: RuleSet = RuleSet([])  # can be changed at any time to provide a new set of rules.
        self.events: list[Event] = []  # defaults to empty... but nothing will work properly

        # causality tracking controls
        self.build_multiway_space_links: bool = True

        # progress tracking attributes
        self.n_step_progress: float = 0  # percentage of steps run by some_method_n().

        # Signals (can be used to live update analysis objects like the causal graph)
        self.on_evolved_step: Signal = Signal()
        self.on_evolved_n: Signal[int] = Signal()  # after all evolves
        self.on_regress_step: Signal = Signal()
        self.on_regress_n: Signal[int] = Signal()  # after all undo's
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
        self.events[0] = Event(
            time=0,
            space_deltas=list(
                (
                    DeltaSpace(i, (i,), (DeltaCell((), ()),), None)
                    for i in initial_space
                )
            )
        )  # initial output space must be `i` as well so that next evolve() works.

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
        """
        applied_rules: list[DeltaSpace] = self.ruleset.apply(tuple(self.current_event.spaces))
        if not any(applied_rules):  # if no rules made any modifications to the spaces
            self.current_event.inert = True
            return

        # Create a new event and process it
        self.events.append(
            Event(self.current_event.time + 1, space_deltas=applied_rules)  # create a new event
        )

        # process causal distance to creation
        min_prev: int = min((self.events[e_idx].causal_distance_to_creation
                             for e_idx in self.current_event.causally_connected_events),
                            default=-1)
        self.current_event.causal_distance_to_creation = min_prev + 1

        # construct the Multiway tree
        if self.build_multiway_space_links:
            if len(self.events) > 1:
                parent_event: Event = self.events[-2]
                current_event: Event = self.events[-1]
                for c_delta_space in current_event.space_deltas:
                    for p_delta_space in parent_event.space_deltas:
                        if c_delta_space.input_space in p_delta_space.output_space:
                            c_delta_space.parent_delta = p_delta_space
                            break

        # emit any signals
        self.on_evolved_step.emit()

    def evolve(self, n_steps: int, break_when_inert: bool = False) -> None:
        """Evolve the system n steps."""
        i: int = 0
        self._dirty_thread = False  # must reset
        while i < n_steps:
            # print(str(next(self.current_event.spaces).vec.search_buffer).replace('A', '\x1b[1;41m A \x1b[0m').replace('B', '\x1b[1;42m B \x1b[0m'))  # if we want to see how the buffer changes.
            self.n_step_progress = (i + 1) / n_steps
            i += 1
            self._evolve()
            if break_when_inert and self.current_event.inert:
                break
            if self._dirty_thread:
                break

        # emit any signals
        self.on_evolved_n.emit(n_steps)

    def regress(self, n_steps: int) -> None:
        self._dirty_thread = False  # must reset
        for _ in range(n_steps):
            self.n_step_progress = (_ + 1) / n_steps
            self.events.pop()
            self.on_regress_step.emit()
            if self._dirty_thread:
                break
        self.on_regress_n.emit(n_steps)

    def stop_thread(self):
        """Used to safely interrupt any long-running methods in a thread."""
        self._dirty_thread = True

    def walk_branch(self, branch_coord: Coordinate) -> Iterator[SpaceState]:
        """Each branch has a unique access index (event index, space index)... this is the best way to walk up the event tree from a particular branch leaf."""
        try:
            event: Event = self.events[branch_coord.event_idx]
            g: Iterator[tuple] = event.spaces_with_deltas
            for _ in range(branch_coord.space_idx): next(g)
            t: tuple = next(g)
            branch: DeltaSpace = t[0]
            yield t[2]  # the space at space_idx
            while (nb := branch.parent_delta) is not branch:
                yield branch.input_space
                branch = nb
        except StopIteration:
            raise IndexError("The space index is out of range.")
        except IndexError:
            raise IndexError("The event index is out of range.")

    def find_cell_lifespan(
            self,
            cell_ids: Sequence[int],
            event_range: slice = slice(0, -1)
    ) -> tuple[list[Coordinate | None], list[list[Coordinate]]]:
        """Returns the branch indices of a cell's lifespan."""
        created_at: list[Coordinate] = [None] * len(cell_ids)  # type: ignore
        destroyed_at: list[list[Coordinate]] = [[] for _ in range(len(cell_ids))]  # can be destroyed in multiple branches
        for event_idx in range(*event_range.indices(len(self.events))):
            event: Event = self.events[event_idx]
            for space_idx, (ds, dc, s) in enumerate(event.spaces_with_deltas):
                for i, cell_id in enumerate(cell_ids):
                    if not created_at[i] and cell_id in (c.id for c in dc.new_cells):
                        created_at[i] = Coordinate(event_idx, space_idx)
                    if cell_id in (c.id for c in dc.destroyed_cells):
                        destroyed_at[i].append(Coordinate(event_idx, space_idx))
        return created_at, destroyed_at

    def __str__(self) -> str:
        return '\n'.join(str(e) for e in self.events)


if __name__ == '__main__':
    pass
