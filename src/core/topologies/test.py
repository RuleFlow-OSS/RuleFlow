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
    pass
