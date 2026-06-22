"""Vector Implementation (Custom fit for engine) to be OPTIONALLY used as the Sequence of Cells for the StateSpace.

==== Policy ====
- The API for all vectors should be cross-compatible. If a specific vector implementation is switched, the client code should still work just fine.

==== FUTURE CONSIDERATIONS ====
- Add a new backend for persistent vectors (using Rope or Finger data structures) to solve the structural edit problem
with the current trie-based pvector data structure.
This would likely be a significant time commitment to implement properly... so do this in the future only when truly needed.
    - Consider implementing these in pure C and making a python interface for maximum performance.
"""
from typing import MutableSequence, Sequence, Literal, overload, NamedTuple, Iterator, Callable, Any
from copy import copy
import numpy as np
type Array = np.ndarray[tuple[int]]
# TODO: abstract the finditer
# TODO: update the SpaceState1D
# TODO: make sure all current functionality works with new backend


# Helper
def neutralize(cls):
    """
    Class decorator that overwrites all dunder methods of the parent
    to return 'self' (or 0/False where Python requires strict types).
    """
    def return_self(self, *args, **kwargs):
        return self
    def return_zero(self, *args, **kwargs):
        return 0
    def return_false(self, *args, **kwargs):
        return False
    safe_list: set[str] = {  # These methods are critical for the object to exist/instantiate. Don't touch them.
        '__new__', '__init__', '__class__', '__getattribute__',
        '__setattr__', '__repr__', '__str__', '__dict__', '__doc__'
    }
    for name in dir(bytearray):
        if name in safe_list:
            continue
        if name.startswith("__") and name.endswith("__"):
            # Handle specific type constraints enforced by Python C-API
            if name in ('__bool__',):
                setattr(cls, name, return_false)
            elif name in ('__len__', '__hash__', '__index__', '__int__'):
                setattr(cls, name, return_zero)
            elif name in ('__float__',):
                setattr(cls, name, lambda self: 0.0)
            else:
                setattr(cls, name, return_self)
    return cls


@neutralize
class NullByteArray(bytearray):
    def __init__(self, *args, **kwargs):
        super().__init__()

    # We also override __getattribute__ to swallow named methods like .append() or .decode()
    def __getattribute__(self, name):
        # Allow access to internal structure if absolutely needed, otherwise return self
        if name in ('__class__', '__dict__', '__repr__'):
            return super().__getattribute__(name)
        # Return a lambda that swallows arguments and returns self
        return lambda *args, **kwargs: self

    def __repr__(self):
        return "<NullByteArray>"


# ================================ Target Bytes Cache ================================
# IMPORTANT NOTE: Sequence[Cell] must really be tuple[Cell] for there to be any benefit to using the Cache!!! Because tuple is hashable.
_bytes_cache_size: int = 1024
_bytes_cache = {  # FIFO cache
    # globally cached bytes will go here where the key is an immutable array of Cells and the value is the compiled bytes
}
def _retrieve_bytes(key: Sequence[Cell]) -> bytes:
    """Used to retrieve the pre-compiled bytearrays from the global cache (fills up quickly for our application)."""
    pass
def enable_bytes_cache(b: bool, cache_size: int = _bytes_cache_size):
    """Enable the use of the global bytes cache. Consider disabling the cache if there is an unknown number of bytes sequences to be used."""
    if b:
        global _bytes_cache_size
        _bytes_cache_size = cache_size
        def retrieve_bytes(key: Sequence[Cell]) -> bytes:
            global _bytes_cache
            try:  # we use this because the cache "hit" is most common for our systems... so a bit faster than doing an if statement when key exists in the cache already.
                return _bytes_cache[key]
            except KeyError:
                if len(_bytes_cache) >= _bytes_cache_size:  # ensure that the cache stays within limits
                    try:
                        del _bytes_cache[next(iter(_bytes_cache))]  # use the fact that dicts keep element order to follow FIFO caching principles
                    except (StopIteration, RuntimeError, KeyError):
                        pass
                _bytes_cache[key] = (r := bytes(ord(c.quanta) for c in key))
                return r
            except TypeError:  # if key is not hashable:  # but it really-really ought to be!
                return retrieve_bytes(tuple(key))
    else:
        def retrieve_bytes(key: Sequence[Cell]) -> bytes:
            return bytes(ord(c.quanta) for c in key)
    globals()['_retrieve_bytes'] = retrieve_bytes
enable_bytes_cache(True)
_search_buffer_enabled: bool = True
_bytearray: type[bytearray | NullByteArray] = NullByteArray  # default is the "blackhole"
def enable_search_buffer(b: bool):
    global _search_buffer_enabled, _bytearray
    if b != _search_buffer_enabled:
        globals()['bytearray'], _bytearray = _bytearray, bytearray
        _search_buffer_enabled = b


# ================================ Regex Backend ================================
import re
import regex
from regex import compile  # the default regex compiler
def set_regex_backend(m: Literal['re', 'regex']):
    """Set the regex backend to either the builtin `re` or the more versatile `regex` (default)"""
    if m == 'regex':
        globals()['compile'] = regex.compile
    elif m == 're':
        globals()['compile'] = re.compile
def set_regex_compiler_args(*args, **kwargs):
    """Sets the default args for the regex compiler that compiles patterns."""
    global _regex_compiler_args
    _regex_compiler_args = args, kwargs
def set_regex_find_args(*args, **kwargs):
    """Sets the default arguments for the Pattern.find_<type>() function."""
    global _regex_find_args
    _regex_find_args = args, kwargs
_regex_compiler_args: tuple[tuple, dict] = ((), {})
_regex_find_args: tuple[tuple, dict] = ((), {})
_pattern_encoding: str = 'ascii'
_pattern_cache_size: int = 1024
_pattern_cache: dict[str | bytes, re.Pattern | regex.Pattern] = {}
def _retrieve_pattern(p: str | bytes) -> re.Pattern | regex.Pattern:
    """Used to retrieve the pre-compiled patterns."""
    pass  # p must really be bytes for the compiled pattern to work on the bytearray search buffer... the cache takes care of this.
def enable_pattern_cache(b: bool, cache_size: int = _pattern_cache_size):
    """Enable the use of the global pattern cache. Consider disabling the cache if there is an unknown number of patterns to be used."""
    if b:
        global _pattern_cache_size
        _pattern_cache_size = cache_size
        def retrieve_pattern(p: str | bytes) -> re.Pattern | regex.Pattern:
            global _pattern_cache
            try:  # we use this because the cache "hit" is most common for our systems... so a bit faster than doing an if statement when key exists in the cache already.
                return _pattern_cache[p]
            except KeyError:
                if len(_pattern_cache) >= _pattern_cache_size:  # ensure that the cache stays within limits
                    try:
                        del _pattern_cache[next(iter(_pattern_cache))]  # use the fact that dicts keep element order to follow FIFO caching principles
                    except (StopIteration, RuntimeError, KeyError):
                        pass
                _pattern_cache[p] = (r:=compile(p if isinstance(p, bytes) else bytes(p, _pattern_encoding),
                                                *_regex_compiler_args[0], **_regex_compiler_args[1]))
                return r
    else:
        def retrieve_pattern(p: str | bytes) -> re.Pattern | regex.Pattern:
            if isinstance(p, str):
                p = bytes(p, _pattern_encoding)
            return compile(p, *_regex_compiler_args[0], **_regex_compiler_args[1])
    globals()['_retrieve_pattern'] = retrieve_pattern
enable_pattern_cache(True)
def finditer(pattern: str | bytes, search_buffer: bytearray) -> Iterator[re.Match | regex.Match]:
    return _retrieve_pattern(pattern).finditer(search_buffer, *_regex_find_args[0], **_regex_find_args[1])


# ================================ Vector Implementation ================================

# Long-term TODO: think about and implement this memory efficient storage data structure...
# class Piece(NamedTuple):
#     method: Callable
#     args: tuple[Any]
#     kwargs: dict[str, Any]
#
#
# class CellVectorVault:
#     def __init__(self, data: Sequence[int]):
#         self.vault: CellVector               # the original read-only data
#         self.frontier: Vector                # the latest update (so that searches are efficient)
#         self.pieces: list[Piece] = []        # the updates stored as pieces for this branch
#         self.parent_branch: CellVectorVault  # the current checkpoint


class Vector(MutableSequence):
    def __init__(self, data: Sequence[int], dtype: np.unsignedinteger = np.uint8):
        self.logical_length: int = len(data)
        # Allocate 1.5x space, with a minimum buffer so tiny arrays don't break
        self.capacity: int = self.logical_length
        self.data: Array = np.zeros(self.capacity, dtype=dtype)
        self.data[:self.logical_length] = data

    @property
    def logical_data(self) -> Array:
        return self.data[:self.logical_length]

    def __len__(self) -> int:
        return self.logical_length

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> Array: ...

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
                new_space: Array = np.zeros(self.capacity, dtype=self.data.dtype)
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


class Cell(NamedTuple):
    vec: CellVector
    index: int

    @property
    def quanta(self) -> int:
        return self.vec.data[self.index]

    @quanta.setter
    def quanta(self, value: int) -> None:
        self.vec.data[self.index] = value

    @property
    def created_at(self) -> int:
        return self.vec.created_at[self.index]

    @created_at.setter
    def created_at(self, value: int) -> None:
        self.vec.created_at[self.index] = value

    @property
    def id(self) -> int:
        return self.vec.ids[self.index]

    @id.setter
    def id(self, value: int) -> None:
        self.vec.ids[self.index] = value


class CellVector(MutableSequence):
    def __init__(self, data: Sequence[int], id_start: int = 0, dtype: np.unsignedinteger = np.uint8):
        self.data: Vector = Vector(data, dtype=dtype)
        _dtype: np.uint64 = np.uint64
        self.created_at: Vector = Vector(np.zeros(len(self.data), dtype=_dtype), dtype=_dtype)
        self.ids: Vector = Vector(np.arange(id_start, id_start + len(self.data), dtype=_dtype), dtype=_dtype)
        self.id_start: int = len(self.data)

    @property
    def as_cells(self) -> Iterator[Cell]:
        for i in range(len(self.data)):
            yield Cell(self, i)

    @overload
    def get_cell(self, index: int) -> Cell: ...

    @overload
    def get_cell(self, index: slice) -> Iterator[Cell]: ...

    def get_cell(self, index):
        if isinstance(index, slice):
            for i in range(*index.indices(len(self.data))):
                yield Cell(self, i)
            return None
        else:
            return Cell(self, index)

    def next_gen(self) -> CellVector:
        """Return a copy of the current cell vector."""
        return copy(self)  # shallow copy (attributes share)

    def __len__(self) -> int:
        return len(self.data)

    @overload
    def __getitem__(self, index: int) -> int: ...

    @overload
    def __getitem__(self, index: slice) -> Array: ...

    def __getitem__(self, index):
        return self.data[index]

    @overload
    def __setitem__(self, index: int, value: int) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Sequence[int]) -> None: ...

    def __setitem__(self, index, value) -> None:
        if isinstance(index, slice):
            self.data[index] = value
            self.created_at[index] = np.zeros(len(value))  # remember that we are not responsible for updating/correcting this attribute
            self.ids[index] = np.arange(self.id_start, self.id_start + len(value))
            self.id_start += len(value)
        else:
            self.data[index] = value
            self.created_at[index] = 0  # remember that we are not responsible for updating/correcting this attribute
            self.ids[index] = self.id_start
            self.id_start += 1

    def __delitem__(self, index: int | slice):
        # propagate to each attribute
        self.data.__delitem__(index)
        self.created_at.__delitem__(index)
        self.ids.__delitem__(index)

    def insert(self, index: int, value: int) -> None:
        self[index:index] = (value,)

    def __str__(self) -> str:
        return str(self.data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"


if __name__ == '__main__':
    a = CellVector([1, 2, 3, 4, 5, 6])
    print(a.data)
    print(a.ids)
    print('====')
    a[-2:] = [4, 3, 2, 1]
    print(a.data)
    print(a.ids)
    print('====')
    a.append(12)
    print(a.data)
    print(a.ids)
