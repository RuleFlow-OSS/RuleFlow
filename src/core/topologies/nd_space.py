"""This module implement certain N-dimensional space states."""
from typing import Literal
from collections.abc import Sequence
from core.engine import SpaceState, DeltaCell, Cell
from core.topologies.vector import CellVector, CellVectorVault
type VectorBackendType = Literal["vector", "vector_vault"]


class SpaceState1D(SpaceState):
    """A SpaceState for a single dimensions (string) of space units (cells)."""
    __slots__ = 'vec',

    def __init__(self, cells: Sequence[int], vector_backend: VectorBackendType = "vector") -> None:
        self.vec: CellVector = {
            'vector': CellVector,
            'vector_vault': CellVectorVault
        }[vector_backend](cells)

    def __str__(self):
        return str(self.vec)

    def __repr__(self):
        return f'{self.__class__.__name__}({self.vec})'

    @property  # TODO: maybe cache this
    def topology(self) -> CellVector:
        return self.vec

    def next_gen(self) -> SpaceState1D:
        new_space: SpaceState1D = object.__new__(SpaceState1D)
        new_space.vec = self.vec.next_gen()
        return new_space

    # ==== Custom Modifiers ====
    def substitute(self, selector: tuple[int, int], new: Sequence[int]) -> DeltaCell:
        k: slice = slice(*selector)
        self.vec[k] = new
        return DeltaCell(
            tuple(self.vec.prev_gen.get_cells(k)),
            tuple(self.vec.get_cells(slice(k.start, k.start + len(new))))
        )

    def overwrite(self, selector: int, new: Sequence[int]) -> DeltaCell:
        destroyed_cells: list[Cell] = []
        new_cells: list[Cell] = []
        if selector < 0:
            selector = len(self.vec) + selector
        for i in range(len(new)):
            quanta: int = new[i]
            if quanta == -1:  # skip these
                continue
            try:
                idx = selector + i
                self.vec[idx] = new[i]
                destroyed_cells.append(self.vec.prev_gen.get_cell(idx))
                new_cells.append(self.vec.get_cell(idx))
            except IndexError:
                self.vec.append(quanta)
                new_cells.append(self.vec.get_cell(-1))
        return DeltaCell(tuple(destroyed_cells), tuple(new_cells))

    def insert(self, selector: int, new: Sequence[int]) -> DeltaCell:
        if selector < 0:
            selector = len(self.vec) + selector + 1
        self.vec[selector:selector] = new
        return DeltaCell((), tuple(self.vec.get_cells(slice(selector, len(new)))))

    def delete(self, selector: tuple[int, int]) -> DeltaCell:
        k: slice = slice(*selector)
        self.vec[k] = ()
        return DeltaCell(tuple(self.vec.prev_gen.get_cells(k)), ())


class SpaceState2D(SpaceState):
    """It is here that we implement the 2D SpaceState. Just a placeholder for now."""
    pass


class SpaceState3D(SpaceState):
    """It is here that we implement the 3D SpaceState. Just a placeholder for now."""
    pass


if __name__ == '__main__':
    pass
    # s = SpaceState1D([1, 2, 3, 4])
    # print(s, repr(s))
    # print(isinstance(s.vec, Topology))
