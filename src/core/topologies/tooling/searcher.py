"""Implements finding algorithms on pure numpy vectors."""
import re
from collections.abc import Callable

try:
    import regex
except ImportError:
    regex = re
from typing import Literal, Iterator, Any, Sequence, Union
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
try:
    from numba import njit
    NUMBA_AVAILABLE: bool = True
except ImportError:
    NUMBA_AVAILABLE: bool = False
    def njit(*args, **kwargs):
        """Dummy decorator for environments without Numba installed."""
        def decorator(func):
            return func
        # Check if used as @njit without parentheses
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return decorator


type PureVector = np.ndarray[tuple[int]]


# ================================ Regex Vector Search ================================
type RegexPattern = Union[re.Pattern, regex.Pattern]


class VectorRegexSearch:
    """Implements a regex finding algorithm on pure numpy vectors."""

    def __init__(
        self, backend: Literal['re', 'regex'] = 'regex',
        use_pattern_cache: bool = True,
        pattern_cache_size: int = 1024
    ):
        """
        Initializes the regex searcher for numpy vectors.
        All settings and caches are instance-specific.
        """
        self.regex_module = regex if backend == 'regex' else re
        self._use_pattern_cache = use_pattern_cache
        self._pattern_cache_size = pattern_cache_size
        self._pattern_cache: dict[bytes, Any] = {}

        self._compiler_args: tuple[tuple, dict] = ((), {})
        self._find_args: tuple[tuple, dict] = ((), {})

    def set_backend(self, m: Literal['re', 'regex']) -> None:
        """Set the regex backend to either the builtin `re` or the more versatile `regex`."""
        if m == 'regex' and regex is re:
            raise ImportError("The 'regex' package is not installed.")
        self.regex_module = regex if m == 'regex' else re

    def set_compiler_args(self, *args, **kwargs) -> None:
        """Sets the default args for the regex compiler that compiles patterns."""
        self._compiler_args = args, kwargs

    def set_find_args(self, *args, **kwargs) -> None:
        """Sets the default arguments for the regex finditer functionality."""
        self._find_args = args, kwargs

    def enable_pattern_cache(self, enable: bool, cache_size: int | None = None) -> None:
        """
        Enable or disable the instance pattern cache.
        Consider disabling the cache if an unbounded number of patterns will be evaluated.
        """
        self._use_pattern_cache = enable
        if cache_size is not None:
            self._pattern_cache_size = cache_size
        if not enable:
            self._pattern_cache.clear()

    def clear_pattern_cache(self):
        """Call to clear the pattern cache. Should be used if the compiler args are changed."""
        self._pattern_cache.clear()

    @staticmethod
    def normalize_pattern(p: PureVector | str | bytearray | Sequence[int] | bytes) -> bytes:
        if isinstance(p, np.ndarray):
            return p.tobytes()
        elif isinstance(p, str):
            return p.encode()
        elif isinstance(p, bytearray | Sequence):
            return np.array(p).tobytes()
        else:
            return p  # type: ignore

    def _retrieve_pattern(self, p: bytes) -> RegexPattern:
        """Retrieves or compiles the pattern, utilizing the instance cache if enabled."""
        if not self._use_pattern_cache:
            return self.regex_module.compile(
                p,
                *self._compiler_args[0],
                **self._compiler_args[1]
            )
        try:
            return self._pattern_cache[p]
        except KeyError:
            if len(self._pattern_cache) >= self._pattern_cache_size:
                try: del self._pattern_cache[next(iter(self._pattern_cache))]  # FIFO cache eviction
                except (StopIteration, RuntimeError, KeyError): pass
            compiled = self.regex_module.compile(p, *self._compiler_args[0], **self._compiler_args[1])
            self._pattern_cache[p] = compiled
            return compiled

    def __call__(self, pattern: bytes, search_buffer: PureVector | bytearray | bytes) -> Iterator[re.Match | regex.Match]:
        """
        Executes the regex finditer functionality. If the search_buffer is a np.ndarray, it must be c contiguous.
        Treats the array memory directly as a byte buffer.
        """
        compiled_pattern: RegexPattern = self._retrieve_pattern(pattern)

        # memoryview creates an O(1) non-copying view into the numpy array's contiguous memory
        # Python's `re` and `regex` libraries can search buffer-protocol objects natively.
        buffer_view = memoryview[int](search_buffer)
        return compiled_pattern.finditer(buffer_view, *self._find_args[0], **self._find_args[1])


# ================================ Literal Sub-Vector Search ================================
@njit
def _kmp_core(pattern: np.ndarray, search_buffer: np.ndarray, overlapping: bool) -> Iterator[int]:
    """JIT-compiled core loop for the KMP algorithm."""
    p_len: int = len(pattern)
    b_len: int = len(search_buffer)

    lps = np.zeros(p_len, dtype=np.int64)
    length: int = 0
    i: int = 1

    while i < p_len:
        if pattern[i] == pattern[length]:
            length += 1
            lps[i] = length
            i += 1
        else:
            if length != 0:
                length = lps[length - 1]
            else:
                lps[i] = 0
                i += 1

    i: int = 0
    j: int = 0
    while (b_len - i) >= (p_len - j):
        if pattern[j] == search_buffer[i]:
            j += 1
            i += 1

        if j == p_len:
            yield i - j
            if not overlapping:
                j = 0
            else:
                j = lps[j - 1]
        elif i < b_len and pattern[j] != search_buffer[i]:
            if j != 0:
                j = lps[j - 1]
            else:
                i += 1


@njit
def _rabin_karp_core(pattern: np.ndarray, search_buffer: np.ndarray, overlapping: bool) -> Iterator[int]:
    """JIT-compiled core loop for the Rabin-Karp algorithm."""
    p_len: int = len(pattern)
    b_len: int = len(search_buffer)
    base: int = 256
    prime: int = 1000000007

    h: int = 1
    for _ in range(p_len - 1):
        h = (h * base) % prime

    p_hash: int = 0
    t_hash: int = 0

    # Calculate initial hashes
    for i in range(p_len):
        p_hash = (base * p_hash + int(pattern[i])) % prime
        t_hash = (base * t_hash + int(search_buffer[i])) % prime

    i: int = 0
    while i <= b_len - p_len:
        match_found: bool = False
        if p_hash == t_hash:
            match: bool = True
            for k in range(p_len):
                if search_buffer[i + k] != pattern[k]:
                    match = False
                    break
            if match:
                yield i
                match_found = True

        if match_found and not overlapping:
            i += p_len
            if i <= b_len - p_len:
                t_hash = 0
                for k in range(p_len):
                    t_hash = (base * t_hash + int(search_buffer[i + k])) % prime
            continue

        if i < b_len - p_len:
            t_hash = (base * (t_hash - int(search_buffer[i]) * h) + int(search_buffer[i + p_len])) % prime
            if t_hash < 0:
                t_hash += prime

        i += 1


@njit
def _wildcard_naive_core(pattern: np.ndarray, search_buffer: np.ndarray, overlapping: bool) -> Iterator[int]:
    """JIT-compiled naive fallback for KMP and Rabin-Karp when a -1 wildcard is present."""
    p_len: int = len(pattern)
    b_len: int = len(search_buffer)

    i: int = 0
    while i <= b_len - p_len:
        match: bool = True
        for j in range(p_len):
            if pattern[j] != -1 and pattern[j] != search_buffer[i + j]:
                match = False
                break

        if match:
            yield i
            if not overlapping:
                i += p_len
                continue
        i += 1


type VectorSearchBackendType = Literal['numpy', 'c_bytes', 'kmp', 'rabin_karp']
class VectorSearch:
    """
    For highly optimized exact sub-vector matches. Supports -1 as a wildcard.
    Only supports the fastest zero-copy NumPy heuristics and C-level memory implementations.
    """

    def __init__(self, backend: VectorSearchBackendType = 'numpy', overlapping: bool = False):
        """Initializes the literal searcher with a default execution strategy."""
        self._backend_name: VectorSearchBackendType = backend
        self._backend_map: dict[VectorSearchBackendType, Callable[[np.ndarray, np.ndarray], Iterator[tuple[int, int]]]] = {
            'numpy': self._search_numpy,
            'c_bytes': self._search_c_bytes,
            'kmp': self._search_kmp,
            'rabin_karp': self._search_rabin_karp
        }
        self._backend_callback: Callable[[np.ndarray, np.ndarray], Iterator[tuple[int, int]]] = self._backend_map[backend]
        self.overlapping: bool = overlapping

    def set_overlapping_mode(self, b: bool) -> None:
        self.overlapping = b

    def set_backend(self, backend: VectorSearchBackendType) -> None:
        """
        Dynamically switch the underlying search algorithm.

        Choosing the right backend is critical depending on your memory limits and the repetitiveness of your data:

        - 'numpy' (Heuristic):
            * Pros: Zero-copy (highly memory efficient). Extremely fast on data
              with high variance/diversity (e.g., random floats or large IDs).
            * Cons: Degrades severely on highly repetitive data (e.g., arrays of
              mostly zeros), as it filters by first/last elements. Repetitive data
              creates too many candidates, causing memory and CPU spikes.

        - 'c_bytes' (Boyer-Moore-Horspool):
            * Pros: Often the absolute fastest option. Leverages Python's native
              C-optimized string matching. Handles large types (uint64) seamlessly.
            * Cons: High memory overhead. Calls `.tobytes()`, requiring an exact
              1:1 memory copy of the array (e.g., a 2GB array needs 2GB of free RAM).

        - 'kmp' (Knuth-Morris-Pratt):
            * Pros: Zero-copy. Guaranteed O(N + M) time complexity. The safest
              fallback for highly repetitive data or constrained RAM where 'numpy'
              and 'c_bytes' fail.
            * Cons: Slow if Numba is not installed.

        - 'rabin_karp' (Rolling Hash):
            * Pros: Zero-copy. Good alternative for sequence matching.
            * Cons: Requires Numba for speed. Generally outclassed by KMP in
              worst-case scenarios due to potential hash collisions.

        Args:
            backend: The string identifier of the backend to use.
        """
        self._backend_name: VectorSearchBackendType = backend
        self._backend_callback = self._backend_map[backend]

    def _search_numpy(self, pattern: np.ndarray, search_buffer: np.ndarray) -> Iterator[tuple[int, int]]:
        """
        Optimized NumPy heuristic (Zero-Copy).
        Dynamically filters candidates by first/last non-wildcard elements via np.nonzero
        before checking full windows.
        """
        p_len: int = len(pattern)
        b_len: int = len(search_buffer)
        if p_len > b_len or p_len == 0:
            return

        wildcard_mask = (pattern == -1)
        has_wildcard = bool(wildcard_mask.any())

        # Fast path if the pattern is entirely wildcards
        if has_wildcard and wildcard_mask.all():
            last_end: int = -1
            for idx in range(b_len - p_len + 1):
                if not self.overlapping and idx < last_end:
                    continue
                yield idx, idx + p_len
                last_end = idx + p_len
            return

        # Find the best anchors to filter by (first and last non-wildcard elements)
        if has_wildcard:
            non_wildcards = np.nonzero(np.logical_not(wildcard_mask))[0]
            first_fixed_idx = int(non_wildcards[0])
            last_fixed_idx = int(non_wildcards[-1])
        else:
            first_fixed_idx = 0
            last_fixed_idx = p_len - 1

        first_val = pattern[first_fixed_idx]
        last_val = pattern[last_fixed_idx]

        # Filter by first fixed element
        first_elem_matches = np.nonzero(search_buffer[:b_len - p_len + 1 + first_fixed_idx] == first_val)[0]

        # Shift candidate indices back to the start of the pattern window
        candidates = first_elem_matches - first_fixed_idx

        # Filter out candidates that would cause out-of-bounds reading
        valid_bounds = (candidates >= 0) & (candidates <= b_len - p_len)
        candidates = candidates[valid_bounds]

        if len(candidates) == 0:
            return

        # Filter remaining candidates by last fixed element
        if first_fixed_idx != last_fixed_idx:
            last_elem_offsets = candidates + last_fixed_idx
            last_elem_matches = search_buffer[last_elem_offsets] == last_val
            candidates = candidates[last_elem_matches]

        if len(candidates) == 0:
            return

        # Validate surviving candidates utilizing sliding window view
        windows = sliding_window_view(search_buffer, p_len)
        candidate_windows = windows[candidates]

        if has_wildcard:
            valid_mask = ((candidate_windows == pattern) | wildcard_mask).all(axis=1)
        else:
            valid_mask = (candidate_windows == pattern).all(axis=1)

        final_matches = candidates[valid_mask]

        # Handle yielding and overlap filtering
        last_end: int = -1
        for idx in final_matches:
            if not self.overlapping and idx < last_end:
                continue
            yield int(idx), int(idx + p_len)
            last_end = idx + p_len

    def _search_c_bytes(self, pattern: np.ndarray, search_buffer: np.ndarray) -> Iterator[tuple[int, int]]:
        """
        Leverages Python's native C string matching (Boyer-Moore-Horspool).
        *Note: Has a memory overhead of creating a byte representation of the array.*
        """
        p_len: int = len(pattern)
        b_len: int = len(search_buffer)
        if p_len > b_len or p_len == 0:
            return None
        if (pattern == -1).any():
            return self._search_numpy(pattern, search_buffer)

        itemsize = search_buffer.itemsize
        pattern_bytes = pattern.tobytes()
        buffer_bytes = search_buffer.tobytes()

        start_byte = 0
        while True:
            # Executes at C-level speeds using highly optimized algorithms
            idx = buffer_bytes.find(pattern_bytes, start_byte)
            if idx == -1:
                break

            # CRITICAL: Since we are matching raw memory bytes, a sequence might accidentally
            # match across the boundaries of two large integers (misalignment).
            if idx % itemsize == 0:
                array_idx = idx // itemsize
                yield array_idx, array_idx + p_len
                # Advance pointer based on overlap rules
                start_byte = idx + (itemsize if self.overlapping else (p_len * itemsize))
            else:
                # Misaligned match. Advance by 1 byte to continue searching
                start_byte = idx + 1

    def _search_kmp(self, pattern: np.ndarray, search_buffer: np.ndarray) -> Iterator[tuple[int, int]]:
        """KMP exact string matching, accelerated by Numba JIT when available."""
        p_len: int = len(pattern)
        if p_len > len(search_buffer) or p_len == 0:
            return

        if (pattern == -1).any():
            for start_idx in _wildcard_naive_core(pattern, search_buffer, self.overlapping):
                yield int(start_idx), int(start_idx + p_len)
        else:
            for start_idx in _kmp_core(pattern, search_buffer, self.overlapping):
                yield int(start_idx), int(start_idx + p_len)

    def _search_rabin_karp(self, pattern: np.ndarray, search_buffer: np.ndarray) -> Iterator[tuple[int, int]]:
        """Rabin-Karp rolling hash algorithm, accelerated by Numba JIT when available."""
        p_len: int = len(pattern)
        if p_len > len(search_buffer) or p_len == 0:
            return

        if (pattern == -1).any():
            for start_idx in _wildcard_naive_core(pattern, search_buffer, self.overlapping):
                yield int(start_idx), int(start_idx + p_len)
        else:
            for start_idx in _rabin_karp_core(pattern, search_buffer, self.overlapping):
                yield int(start_idx), int(start_idx + p_len)

    def __call__(self, pattern: PureVector, search_buffer: PureVector) -> Iterator[tuple[int, int]]:
        """
        Executes the exact literal search on the array using the selected backend strategy.
        Yields (start, stop) index spans.
        """
        if not isinstance(pattern, np.ndarray) or not isinstance(search_buffer, np.ndarray):
            raise TypeError("Both pattern and search_buffer must be NumPy ndarrays.")
        if pattern.ndim != 1 or search_buffer.ndim != 1:
            raise ValueError("VectorSearch currently supports 1D vectors only.")
        if pattern.dtype != search_buffer.dtype:
            pattern = pattern.astype(search_buffer.dtype)
        return self._backend_callback(pattern, search_buffer)


class VectorSymbolicAutomatonSearch:
    """For large alphabet sub-vector matching (basically generalized regex using automatons)"""
    pass


if __name__ == "__main__":
    pass
    # print("==== Test the VectorRegexSearch ====")
    # text = b"hello world, hello numpy! regex is fast on pure vectors."
    # buffer = np.frombuffer(text, dtype=np.uint8)
    # print(buffer)
    #
    # # Instantiate the searcher
    # searcher = VectorRegexSearch(backend='regex')
    #
    # print("--- Test 1: String Pattern ---")
    # # Testing standard string pattern
    # for match in searcher(searcher.normalize_pattern("hello"), buffer):
    #     print(f"Found 'hello' at span: {match.span()} - Bytes: {match.group()}")
    #
    # print("\n--- Test 2: Bytes Pattern (with Regex) ---")
    # # Testing bytes pattern with regex characters
    # for match in searcher(b"re[a-z]+", buffer):
    #     print(f"Found regex match at span: {match.span()} - Bytes: {match.group()}")
    #
    # print("\n--- Test 3: Numpy Array Pattern ---")
    # # Testing passing a numpy array directly as the pattern
    # pattern_arr = searcher.normalize_pattern(np.frombuffer(b"pure", dtype=np.uint8))
    # for match in searcher(pattern_arr, buffer):
    #     print(f"Found 'pure' from array pattern at span: {match.span()} - Bytes: {match.group()}")




    # print("===== Testing VectorSearch =====")
    #
    # # The backends we preserved in the optimization sweep
    # available_backends = ['c_bytes', 'numpy', 'kmp', 'rabin_karp']
    #
    # # --- Test 1: Standard Search (Int32) ---
    # print("\n--- Test 1: Standard Search (Int32, Non-Overlapping) ---")
    # int_buffer = np.array([10, 20, 30, 40, 20, 30, 50, 20, 30, 40, 60], dtype=np.int32)
    # int_pattern = np.array([20, 30, 40], dtype=np.int32)
    #
    # print(f"Buffer:  {int_buffer}")
    # print(f"Pattern: {int_pattern}")
    #
    # for backend in available_backends:
    #     searcher = VectorSearch(backend=backend, overlapping=False)
    #     matches = list(searcher(int_pattern, int_buffer))
    #     print(f"\n[{backend}] Spans: {matches}")
    #     for start, end in matches:
    #         print(f"    -> Extracted match: {int_buffer[start:end]}")
    #
    # # --- Test 2: Overlapping vs Non-Overlapping (Float64) ---
    # print("\n--- Test 2: Overlapping vs Non-Overlapping (Float64) ---")
    # float_buffer = np.array([1.5, 1.5, 1.5, 1.5, 1.5], dtype=np.float64)
    # float_pattern = np.array([1.5, 1.5, 1.5], dtype=np.float64)
    #
    # print(f"Buffer:  {float_buffer}")
    # print(f"Pattern: {float_pattern}")
    #
    # for backend in available_backends:
    #     searcher_no_ov = VectorSearch(backend=backend, overlapping=False)
    #     searcher_ov = VectorSearch(backend=backend, overlapping=True)
    #
    #     matches_no_ov = list(searcher_no_ov(float_pattern, float_buffer))
    #     matches_ov = list(searcher_ov(float_pattern, float_buffer))
    #
    #     print(f"[{backend}] No-Overlap: {matches_no_ov} | Overlap: {matches_ov}")
    #
    # # --- Test 3: Auto-Casting Pattern Dtype ---
    # print("\n--- Test 3: Auto-Casting Pattern Dtype ---")
    # uint64_buffer = np.array([10, 20, 30, 40], dtype=np.uint64)
    # int8_pattern = np.array([20, 30], dtype=np.int8)
    #
    # print(f"Buffer (uint64): {uint64_buffer}")
    # print(f"Pattern (int8 before search): {int8_pattern}")
    #
    # # We will test this specifically on 'c_bytes' since it requires precise memory alignment
    # searcher_cast = VectorSearch(backend='c_bytes')
    # matches_cast = list(searcher_cast(int8_pattern, uint64_buffer))
    # print(f"[c_bytes] Matches after auto-cast to uint64: {matches_cast}")
    #
    # # --- Test 4: Edge Cases ---
    # print("\n--- Test 4: Edge Cases (Backend: kmp) ---")
    # edge_searcher = VectorSearch(backend='kmp')
    # base_buffer = np.array([1, 2, 3, 4, 5], dtype=np.int32)
    # print(f"Base Buffer: {base_buffer}")
    #
    # # 1. Pattern > Buffer
    # large_pat = np.array([1, 2, 3, 4, 5, 6], dtype=np.int32)
    # print(f"  Pattern > Buffer {large_pat} -> Matches: {list(edge_searcher(large_pat, base_buffer))}")
    #
    # # 2. Pattern Length 1
    # single_pat = np.array([3], dtype=np.int32)
    # print(f"  Pattern Length 1 {single_pat} -> Matches: {list(edge_searcher(single_pat, base_buffer))}")
    #
    # # 3. No Match
    # no_match_pat = np.array([9, 9], dtype=np.int32)
    # print(f"  No Match {no_match_pat} -> Matches: {list(edge_searcher(no_match_pat, base_buffer))}")
    #
    # # 4. Empty Pattern
    # empty_pat = np.array([], dtype=np.int32)
    # print(f"  Empty Pattern {empty_pat} -> Matches: {list(edge_searcher(empty_pat, base_buffer))}")
    #
    # # --- Test 5: 1-Byte Array Support Verification ---
    # print("\n--- Test 5: 1-Byte Array Support Verification ---")
    # print("Ensuring 1-byte arrays (uint8) still run smoothly despite being multi-byte focused.")
    # uint8_buffer = np.array([255, 128, 255, 128, 0], dtype=np.uint8)
    # uint8_pattern = np.array([255, 128], dtype=np.uint8)
    #
    # print(f"Buffer:  {uint8_buffer}")
    # print(f"Pattern: {uint8_pattern}")
    #
    # for backend in available_backends:
    #     searcher_1b = VectorSearch(backend=backend)
    #     print(f"[{backend}] Matches: {list(searcher_1b(uint8_pattern, uint8_buffer))}")
