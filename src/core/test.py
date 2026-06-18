import numpy as np
from numpy.typing import NDArray
from typing import Sequence


class Vector:
    def __init__(self, data: Sequence[int], dtype: np.unsignedinteger = np.uint8):
        self.logical_length: int = len(data)
        # Allocate 1.5x space, with a minimum buffer so tiny arrays don't break
        self.capacity: float | int = max(int(self.logical_length * 1.5), 16)
        self.space: NDArray = np.zeros(self.capacity, dtype=dtype)
        self.space[:self.logical_length] = data

    @property
    def active_space(self) -> np.ndarray:
        """Always use this when passing data to Regex or Math engines!"""
        return self.space[:self.logical_length]

    def __len__(self) -> int:
        return self.logical_length

    def __getitem__(self, index: int | slice) -> np.ndarray | int:
        """Allows reading: `val = vec[5]` or `sub_array = vec[2:5]`"""
        return self.active_space[index]

    def __setitem__(self, index: int | slice, value: Sequence[int] | int):
        """
        The Unified Master Modifier.
        Handles Substitutions, Insertions, and Overwrites natively through slice math.
        """
        if isinstance(index, slice):
            start, stop, step = index.indices(self.logical_length)
            value_arr = np.asarray(value, dtype=self.space.dtype)

            if step != 1:
                # Extended slices (e.g., vec[0:5:2] = [1,2,3]) must be exact matches
                if len(value_arr) != len(range(start, stop, step)):
                    raise ValueError("attempt to assign sequence of size X to extended slice of size Y")
                self.active_space[index] = value_arr
                return

            length_to_remove = stop - start
            new_len = len(value_arr)
            delta = new_len - length_to_remove  # The net change in array size

            # Reallocation trigger
            if self.logical_length + delta > self.capacity:
                self.capacity = max(int(self.capacity * 1.5), self.logical_length + delta)
                new_space = np.zeros(self.capacity, dtype=self.space.dtype)
                new_space[:self.logical_length] = self.space[:self.logical_length]
                self.space = new_space

            # Shift existing data (One shift only!)
            if delta != 0:
                # We move the data that sits AFTER the slice to its new home
                tail_start = stop
                tail_end = self.logical_length
                new_tail_start = start + new_len
                new_tail_end = new_tail_start + (tail_end - tail_start)

                # NumPy safely handles overlapping memory during this slice assignment
                self.space[new_tail_start:new_tail_end] = self.space[tail_start:tail_end]

            # Write new data
            if new_len > 0:
                self.space[start: start + new_len] = value_arr

            self.logical_length += delta

        else:
            # Handle standard single-integer assignment: `vec[5] = 42`
            if index < 0: index += self.logical_length
            if index < 0 or index >= self.logical_length: raise IndexError("NumVec index out of range")
            self.space[index] = value

    def __delitem__(self, index: int | slice):
        """
        The Unified Master Deletion.
        Handles single items and continuous slices seamlessly.
        """
        if isinstance(index, slice):
            start, stop, step = index.indices(self.logical_length)

            if step == 1:
                length_to_remove = stop - start
                if length_to_remove <= 0:
                    return
                # Shift tail left, closing the gap
                self.space[start: self.logical_length - length_to_remove] = self.space[stop: self.logical_length]
                self.logical_length -= length_to_remove
            else:
                # Fallback for extended slices
                new_active = np.delete(self.active_space, np.s_[index])
                self.logical_length = len(new_active)
                self.space[:self.logical_length] = new_active
        else:
            if index < 0: index += self.logical_length
            if index < 0 or index >= self.logical_length: raise IndexError("NumVec index out of range")

            # Shift tail left by 1
            self.space[index: self.logical_length - 1] = self.space[index + 1: self.logical_length]
            self.logical_length -= 1

    def __str__(self) -> str:
        return str(self.active_space)

    def __repr__(self) -> str:
        return f"NumVec({str(self.active_space)})"


import numpy as np
from typing import Literal, NamedTuple


class Piece(NamedTuple):
    source: Literal['original', 'add']
    start: int
    length: int


class NumpyVault:
    def __init__(self, initial_state: np.ndarray):
        # 1. The Original Buffer (Read-only, immutable)
        self.original_buffer = np.copy(initial_state)

        # 2. The Global Append Buffer (Write-only, massive over-allocation)
        # Start with a massive capacity (e.g., 1 million cells) to avoid reallocations
        self.add_buffer = np.zeros(1_000_000, dtype=np.uint8)
        self.add_pointer = 0

        # 3. The Topology (The actual "Piece Table")
        self.topology = [Piece('original', 0, len(initial_state))]

    def log_edit(self, new_data: np.ndarray):
        """
        Appends new sequence data from ANY branch into the global append buffer.
        Returns the index where it was safely stored.
        """
        length = len(new_data)

        # Expand buffer if we somehow hit the 1-million cell limit
        if self.add_pointer + length > len(self.add_buffer):
            self.add_buffer = np.pad(self.add_buffer, (0, len(self.add_buffer)))

        start_idx = self.add_pointer
        self.add_buffer[start_idx: start_idx + length] = new_data
        self.add_pointer += length

        return start_idx

    def build_lens(self, topology_branch: list[Piece]) -> np.ndarray:
        """
        When a branch needs to be executed, the Vault stitches the pieces
        together into a brand new, flat, contiguous NumPy array for the Lens.
        """
        # Calculate total required length
        total_len = sum(p.length for p in topology_branch)
        lens_array = np.zeros(total_len, dtype=np.uint8)

        # Stitch it together
        cursor = 0
        for p in topology_branch:
            if p.source == 'original':
                lens_array[cursor: cursor + p.length] = self.original_buffer[p.start: p.start + p.length]
            else:
                lens_array[cursor: cursor + p.length] = self.add_buffer[p.start: p.start + p.length]
            cursor += p.length

        return lens_array

if __name__ == '__main__':
    a = Vector([1, 2, 3, 4, 5, 6, 7])
    a[2:] = [1, 2, 3]
    print(a)
