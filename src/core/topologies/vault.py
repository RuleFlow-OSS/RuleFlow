"""In this file we implement memory efficient abstractions of certain data structures."""
from typing import NamedTuple, Iterator, MutableSequence, Sequence, Literal, Callable, Any
import numpy as np
type Array = np.ndarray[tuple[int]]
from core.topologies.vec1 import Vector, Cell, CellVector


class Piece(NamedTuple):
    method: Callable
    args: tuple[Any]
    kwargs: dict[str, Any]


class Vault:
    def __init__(self, data: Sequence[int]):
        self.vault: CellVector  # the original read-only data
        self.frontier: Vector  # the latest update (so that searches are efficient)
        self.pieces: list[Piece] = []  # the updates stored as pieces for this branch
        self.parent_branch: Vault  # the current checkpoint
