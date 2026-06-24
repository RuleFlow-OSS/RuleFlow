"""Vector Implementation (Custom fit for engine) to be used by 1 dimensional SpaceState implementations.

==== Policy ====
- The API for all vector topologies should be cross-compatible.
For any given vector implementation, the client code should continue to work.
"""
from typing import MutableSequence, Sequence, Literal, overload, NamedTuple, Iterator, Callable, Any
from copy import copy
import numpy as np
type PureVector = np.ndarray[tuple[int]]


class Vector(MutableSequence):
    def __init__(self, data: Sequence[int], dtype: np.unsignedinteger = np.uint8):
        self.logical_length: int = len(data)
        # Allocate 1.5x space, with a minimum buffer so tiny arrays don't break
        self.capacity: int = self.logical_length
        self.data: PureVector = np.zeros(self.capacity, dtype=dtype)
        self.data[:self.logical_length] = data

    @property
    def logical_data(self) -> PureVector:
        return self.data[:self.logical_length]

    def __len__(self) -> int:
        return self.logical_length

    def __copy__(self):
        o: Vector = object.__new__(Vector)
        o.logical_length = self.logical_length
        o.capacity = self.capacity
        o.data = self.data.copy()
        return o

    def __iter__(self) -> Iterator[int]:
        return iter(self.logical_data)

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> PureVector: ...

    def __getitem__(self, index):
        return self.data[:self.logical_length][index]

    @overload
    def __setitem__(self, index: int, value: int) -> None:
        ...

    @overload
    def __setitem__(self, index: slice, value: Sequence[int]) -> None:
        ...

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            value: Sequence[int]
            start, stop, step = index.indices(self.logical_length)

            if step != 1:
                # Extended slices (e.g., vec[0:5:2] = [1,2,3]) must be exact matches
                if len(value) != len(range(start, stop, step)):
                    raise ValueError("attempt to assign sequence of size X to extended slice of size Y")
                self.logical_data[index] = value
                return

            length_to_remove: int = stop - start
            new_len: int = len(value)
            delta: int = new_len - length_to_remove  # The net change in array size

            # Reallocation trigger
            if self.logical_length + delta > self.capacity:
                self.capacity = max(int(self.capacity * 1.5), self.logical_length + delta)
                new_space: PureVector = np.zeros(self.capacity, dtype=self.data.dtype)
                new_space[:self.logical_length] = self.data[:self.logical_length]
                self.data = new_space

            # Shift existing data (One shift only!)
            if delta != 0:
                # We move the data that sits AFTER the slice to its new home
                tail_start = stop
                tail_end = self.logical_length
                new_tail_start = start + new_len
                new_tail_end = new_tail_start + (tail_end - tail_start)

                # NumPy safely handles overlapping memory during this slice assignment
                self.data[new_tail_start:new_tail_end] = self.data[tail_start:tail_end]

            # Write new data
            if new_len > 0:
                self.data[start: start + new_len] = value

            self.logical_length += delta

        else:
            # Handle standard single-integer assignment: `vec[5] = 42`
            if index < 0: index += self.logical_length
            if index < 0 or index >= self.logical_length: raise IndexError("Index out of range")
            self.data[index] = value

    def __delitem__(self, index: int | slice) -> None:
        if isinstance(index, slice):
            start, stop, step = index.indices(self.logical_length)

            if step == 1:
                length_to_remove = stop - start
                if length_to_remove <= 0:
                    return
                # Shift tail left, closing the gap
                self.data[start: self.logical_length - length_to_remove] = self.data[stop: self.logical_length]
                self.logical_length -= length_to_remove
            else:
                # Fallback for extended slices
                new_active = np.delete(self.logical_data, index)
                self.logical_length = len(new_active)
                self.data[:self.logical_length] = new_active
        else:
            if index < 0: index += self.logical_length
            if index < 0 or index >= self.logical_length: raise IndexError("Index out of range")

            # Shift tail left by 1
            self.data[index: self.logical_length - 1] = self.data[index + 1: self.logical_length]
            self.logical_length -= 1

    def insert(self, index: int, value: int) -> None:
        self[index:index] = (value,)

    def __str__(self) -> str:
        # noinspection PyStringConversionWithoutDunderMethod
        return str(self.logical_data)

    def __repr__(self) -> str:
        # noinspection PyStringConversionWithoutDunderMethod
        return f"{self.__class__.__name__}({self.logical_data})"


class Cell(NamedTuple):  # implements the Cell Protocol from core.engine
    vec: CellVector
    index: int

    @property
    def quanta(self) -> int:
        return self.vec.data[self.index]

    @quanta.setter
    def quanta(self, value: int) -> None:
        self.vec.data[self.index] = value

    @property
    def generation(self) -> int:
        return self.vec.generations[self.index]

    @generation.setter
    def generation(self, value: int) -> None:
        self.vec.generations[self.index] = value

    @property
    def id(self) -> int:
        return self.vec.ids[self.index]

    @id.setter
    def id(self, value: int) -> None:
        self.vec.ids[self.index] = value


class CellVector(MutableSequence):
    def __init__(self,
                 data: Sequence[int],
                 generation: int = 0,
                 id_start: int | Sequence[int] = 0,
                 dtypes: tuple[np.unsignedinteger, ...] = (np.uint8, np.uint64, np.uint64)):
        self.data: Vector = Vector(data, dtype=dtypes[0])
        self.generations: Vector = Vector(np.full(len(self.data), generation, dtype=dtypes[1]), dtype=dtypes[1])
        if isinstance(id_start, int):
            self.ids: Vector = Vector(np.arange(id_start, id_start + len(self.data), dtype=dtypes[2]), dtype=dtypes[2])
        else:
            if len(data) != len(id_start):
                raise IndexError("Length of id_start must be equal to length of data")
            self.ids: Vector = Vector(id_start, dtype=dtypes[2])
        self.id_start: int = len(self.data)
        self.generation: int = generation

    @property
    def all_cells(self) -> Iterator[Cell]:
        for i in range(len(self.data)):
            yield Cell(self, i)

    def get_cell(self, index: int) -> Cell:
        return Cell(self, index)

    def get_cells(self, index: slice) -> Iterator[Cell]:
        for i in range(*index.indices(len(self.data))):
            yield Cell(self, i)

    def next_gen(self) -> CellVector:
        """Return a copy of the current cell vector."""
        o: CellVector = object.__new__(CellVector)  # shallow copy (attributes share)
        o.data = copy(self.data)
        o.generations = copy(self.generations)
        o.ids = copy(self.ids)
        o.id_start = self.id_start
        o.generation = self.generation + 1
        return o

    def __len__(self) -> int:
        return len(self.data)

    def __iter__(self) -> Iterator[int]:
        return self.data.__iter__()

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> PureVector: ...

    def __getitem__(self, index):
        return self.data[index]

    @overload
    def __setitem__(self, index: int, value: int) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Sequence[int]) -> None: ...

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            self.data[index] = value
            self.generations[index] = np.full(len(value), self.generation)
            self.ids[index] = np.arange(self.id_start, self.id_start + len(value))
            self.id_start += len(value)
        else:
            self.data[index] = value
            self.generations[index] = self.generation
            self.ids[index] = self.id_start
            self.id_start += 1

    def __delitem__(self, index: int | slice):
        # propagate to each attribute
        self.data.__delitem__(index)
        self.generations.__delitem__(index)
        self.ids.__delitem__(index)

    def insert(self, index: int, value: int) -> None:
        self[index:index] = (value,)

    def __str__(self) -> str:
        return str(self.data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"


# ================================ Vault Implementation ================================
# Long-term TODO: think about and implement this memory efficient storage data structure...
# Long-term TODO: implement active-frontier algorithms...
pass
# class Piece(NamedTuple):
#     method: Callable  # needs to be the class method so self is not bound
#     args: tuple[Any]
#     kwargs: dict[str, Any]
#
#
# class CellVectorVault:
#     def __init__(self, data: Sequence[int]):
#         # TODO: the getter should be a generator that leaves persistence up to the caller.
#         self.data: CellVector | None         # the vec actual data
#         self.frontier: Vector                # the latest update (so that searches are efficient)
#         self.pieces: list[Piece] = []        # the updates stored as pieces for this branch
#         self.parent_branch: CellVectorVault  # the current checkpoint
#         self.checkpoint: bool                # whether this vault is a checkpoint
#         self.len: int = len(data)            # the length of the current data


if __name__ == '__main__':
    a = CellVector([1, 2, 3, 4, 5, 6])
    for i in a:
        print(i)
    print(a.data)
    print(a.ids)
    print('====')
    a[-2:] = [4, 3, 2, 1]
    print(a.data)
    print(a.ids)
    print(a.generations)
    print('====')
    b = a.next_gen()
    b.append(12)
    print(b.data)
    print(b.ids)
    print(b.generations)
    print(a)
