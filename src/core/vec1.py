"""Vector Implementation (Custom fit for engine) to be OPTIONALLY used as the Sequence of Cells for the StateSpace.

==== Policy ====
- The API for all vectors should be cross-compatible. If a specific vector implementation is switched, the client code should still work just fine.

==== FUTURE CONSIDERATIONS ====
- Add a new backend for persistent vectors (using Rope or Finger data structures) to solve the structural edit problem
with the current trie-based pvector data structure.
This would likely be a significant time commitment to implement properly... so do this in the future only when truly needed.
    - Consider implementing these in pure C and making a python interface for maximum performance.
"""
from pyrsistent import PVector, pvector
from pyrsistent.typing import PVectorEvolver
from typing import MutableSequence, Sequence, Literal, Iterator, overload
from copy import copy
from core.engine import Cell


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


import numpy as np
from typing import Sequence, TypeAlias, NamedTuple
type Array = np.ndarray[tuple[int]]


class Vector(MutableSequence):
    def __init__(self, data: Sequence[int], dtype: np.unsignedinteger = np.uint8):
        self.logical_length: int = len(data)
        # Allocate 1.5x space, with a minimum buffer so tiny arrays don't break
        self.capacity: float | int = max(int(self.logical_length * 1.5), 16)
        self.data: Array = np.zeros(self.capacity, dtype=dtype)
        self.data[:self.logical_length] = data

    @property
    def logical_data(self) -> Array:
        return self.data[:self.logical_length]

    def __len__(self) -> int:
        return self.logical_length

    def __getitem__(self, index: int | slice) -> np.ndarray | int:
        return self.data[:self.logical_length][index]

    def __setitem__(self, index: int | slice, value: Sequence[int] | int):
        if isinstance(index, slice):
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

    def __delitem__(self, index: int | slice):
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
        self[index:index] = value

    def __str__(self) -> str:
        return str(self.logical_data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.logical_data})"


class Cell(NamedTuple):
    value: int
    created_at: int
    id: int


class CellVector(MutableSequence):
    def __init__(self, data: Sequence[int], id_start: int = 0, dtype: np.unsignedinteger = np.uint8):
        self.data: Array = Vector(data, dtype=dtype)
        _dtype: np.dtype = np.uint64
        self.created_at: Array = Vector(np.zeros(len(self.data), dtype=_dtype), dtype=_dtype)
        self.ids: Array = Vector(np.arange(id_start, id_start + len(self.data), dtype=_dtype), dtype=_dtype)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index: int | slice) -> np.ndarray | int:
        return self.data[index]

    def __setitem__(self, index: int | slice, value: Sequence[int] | int):
        pass

    def __delitem__(self, index: int | slice):
        pass

    def insert(self, index: int, value: int) -> None:
        pass

    def __str__(self) -> str:
        return str(self.data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"




# ================================ Vector Implementation ================================
import numpy as np
from typing import Sequence


class Vec(MutableSequence):
    __slots__ = ('data', 'search_buffer')

    def __init__(self, elems: Sequence[int]):
        self.vec: MutableSequence[Cell] = elems if isinstance(elems, MutableSequence) else list(elems)
        self.search_buffer: bytearray = bytearray((ord(c.quanta) for c in elems))

    def __str__(self):
        return str(self.vec)

    def __repr__(self):
        return str(self)

    # ================ Persistence Method Placeholders ================
    def edit(self):
        """Enter edit mode (for immutable/persistent internal vectors)."""

    def commit(self):
        """Commit changes made while in edit mode (for immutable/persistent internal vectors)."""

    # ================ Branching Methods ================
    def branch(self) -> Vec:
        """Branch the current vector into a new vector"""
        nv: Vec = object.__new__(Vec)
        nv.vec = copy(self.vec)
        nv.search_buffer = self.search_buffer  # note: becomes out-of-date on self after branch
        return nv

    def __copy__(self):
        return self.branch()

    def __deepcopy__(self, memo):  # force it to use self.branch for safety
        return self.branch()

    def refresh_search_buffer(self):
        """Must be called if you want to refresh a dirty search buffer."""
        self.search_buffer = bytearray((ord(c.quanta) for c in self.vec))

    # ================ Viewer Methods ================
    def __len__(self):
        return len(self.vec)

    def __iter__(self):
        self.commit()  # flush any changes
        return iter(self.vec)

    @overload
    def __getitem__(self, index: int) -> Cell: ...

    @overload
    def __getitem__(self, index: slice) -> MutableSequence[Cell]: ...

    def __getitem__(self, index):
        self.commit()  # flush any changes before getting anything...
        return self.vec[index]

    def finditer(self, pattern: str | bytes, group: int = 0) -> Iterator[tuple[int, int]]:
        # group tells span to return for a specific (sub)group within the regex match. 0 is the default and returns the span for the entire match.
        if not _search_buffer_enabled:
            self.commit()  # flush any changes
            buffer = _bytearray((ord(c.quanta) for c in self.vec))  # is bytearray when search buffer is disabled.
        else:
            buffer = self.search_buffer
        for m in finditer(pattern, buffer):
            yield m.span(group)

    # ================ Modifiers ================
    @overload
    def __setitem__(self, index: int, value: Cell) -> None:
        ...

    @overload
    def __setitem__(self, index: slice, value: Sequence[Cell]) -> None:
        ...

    def __setitem__(self, index, value):
        self.vec[index] = value
        self.search_buffer[index] = ord(value.quanta) if isinstance(value, Cell) else _retrieve_bytes(value)

    def __delitem__(self, index: int | slice):
        del self.vec[index]
        del self.search_buffer[index]

    def append(self, value: Cell):
        """Append value to end"""
        self.vec.append(value)
        self.search_buffer.append(ord(value.quanta))

    def extend(self, values: Sequence[Cell]):
        """Extend with values"""
        self.vec.extend(values)
        self.search_buffer.extend(_retrieve_bytes(values))

    def insert(self, index: int, value: Cell):
        """Insert value at index"""
        self.vec.insert(index, value)
        self.search_buffer.insert(index, ord(value.quanta))


class TrieVec(Vec):
    __slots__ = ('evolver',)

    def __init__(self, elems: Sequence[Cell]):
        object.__init__(super())
        self.vec: PVector[Cell] = pvector(elems)
        self.search_buffer: bytearray = bytearray((ord(c.quanta) for c in elems))
        self.evolver: PVectorEvolver[Cell] | None = None

    def __str__(self):
        return 'Vec' + str(self.vec)[7:]

    # Persistence Methods
    def edit(self):  # we use this rather than .is_dirty() to minimize space use of an evolver object.
        if self.evolver is None:
            self.evolver = self.vec.evolver()

    def commit(self):
        if self.evolver is not None:
            self.vec = self.evolver.persistent()
            self.evolver = None

    # Branching Methods
    def branch(self) -> TrieVec:
        """Branch the current vector into a new vector"""
        self.commit()  # flush any changes
        nv: TrieVec = object.__new__(TrieVec)
        nv.vec = self.vec  # we don't need to copy as edit() will do that for us
        nv.evolver = None
        nv.search_buffer = self.search_buffer  # note: becomes dirty on self after branch
        # we could auto enter edit mode here... however, that is not necessary as this should work just fine because it is auto entered upon edits.
        return nv

    # ================ Modifiers ================
    @overload
    def __setitem__(self, index: int, value: Cell) -> None: ...

    @overload
    def __setitem__(self, index: slice, value: Sequence[Cell]) -> None: ...

    def __setitem__(self, index, value):
        if isinstance(index, slice):
            value: Sequence[Cell]
            start, stop, _ = index.indices(len(self.vec))
            if len(value) == stop - start:  # if we can do point updates
                self.edit()
                for i, val in enumerate(value):
                    self.evolver[start + i] = val
            else: # Structural Change: because the evolver cannot handle length changes (deletions or insertions)
                self.commit()  # flush any existing point-updates to the pvec
                self.vec = self.vec[:start] + pvector(value) + self.vec[stop:]  # does not use the Evolver object as this creates a new node.
            self.search_buffer[index] = _retrieve_bytes(value)
            return
        # if isinstance(index, int):
        value: Cell
        self.edit()
        self.evolver[index] = value
        self.search_buffer[index] = ord(value.quanta)

    def __delitem__(self, index: int | slice):
        if isinstance(index, int):
            self[index:index+1] = ()
        else:  # if index is a slice
            self[index] = ()

    def append(self, value: Cell):
        """Append value to end"""
        self.edit()
        self.evolver.append(value)
        self.search_buffer.append(ord(value.quanta))

    def extend(self, values: Sequence[Cell]):
        """Extend with values"""
        self.edit()
        self.evolver.extend(values)
        self.search_buffer.extend(_retrieve_bytes(values))

    def insert(self, index, value):
        """Insert value at index"""
        self[index:index] = (value,)


if __name__ == '__main__':
    a = np.arange(10)
    np.delete()
    print(a)
