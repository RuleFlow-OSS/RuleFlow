"""This module implement certain N-dimensional space states."""
from core.engine import SpaceState, Cell, DeltaCell
from typing import MutableSequence, Sequence, Iterator
from copy import copy


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


class SpaceState3D(SpaceState):
    """It is here that we implement the 3D SpaceState. Just a placeholder for now."""
    pass
