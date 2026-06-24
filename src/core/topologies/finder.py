"""Implements finding algorithms on pure numpy vectors."""
import re
import regex
import numpy as np
from typing import Literal, Iterator, Any, Union
type PureVector = np.ndarray[Any, np.dtype[np.uint8]]


class VectorRegexSearch:
    def __init__(
        self,
        backend: Literal['re', 'regex'] = 'regex',
        pattern_encoding: str = 'ascii',
        use_pattern_cache: bool = True,
        pattern_cache_size: int = 1024
    ):
        """
        Initializes the regex searcher for numpy vectors.
        All settings and caches are instance-specific.
        """
        self.regex_module = regex if backend == 'regex' else re
        self.pattern_encoding = pattern_encoding

        self._use_pattern_cache = use_pattern_cache
        self._pattern_cache_size = pattern_cache_size
        self._pattern_cache: dict[bytes, Any] = {}

        self._compiler_args: tuple[tuple, dict] = ((), {})
        self._find_args: tuple[tuple, dict] = ((), {})

    def set_backend(self, m: Literal['re', 'regex']) -> None:
        """Set the regex backend to either the builtin `re` or the more versatile `regex`."""
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

    def _retrieve_pattern(self, p: Union[str, bytes, np.ndarray]):
        """Retrieves or compiles the pattern, utilizing the instance cache if enabled."""
        # Normalize the pattern to bytes
        if isinstance(p, str):
            p_bytes = p.encode(self.pattern_encoding)
        elif isinstance(p, np.ndarray):
            p_bytes = p.tobytes()
        else:
            p_bytes = p

        if not self._use_pattern_cache:
            return self.regex_module.compile(p_bytes, *self._compiler_args[0], **self._compiler_args[1])

        try:
            return self._pattern_cache[p_bytes]
        except KeyError:
            if len(self._pattern_cache) >= self._pattern_cache_size:
                # FIFO cache eviction
                try:
                    del self._pattern_cache[next(iter(self._pattern_cache))]
                except (StopIteration, RuntimeError, KeyError):
                    pass

            compiled = self.regex_module.compile(p_bytes, *self._compiler_args[0], **self._compiler_args[1])
            self._pattern_cache[p_bytes] = compiled
            return compiled

    def __call__(self, pattern: Union[str, bytes, np.ndarray], search_buffer: Union[np.ndarray, str, bytes]) -> Iterator[re.Match | regex.Match]:
        """
        Executes the regex finditer functionality. If the search_buffer is an np.ndarray, it must be c contiguous.
        Treats the array memory directly as a byte buffer.
        """
        compiled_pattern = self._retrieve_pattern(pattern)

        # memoryview creates an O(1) non-copying view into the numpy array's contiguous memory
        # Python's `re` and `regex` libraries can search buffer-protocol objects natively.
        buffer_view = memoryview(search_buffer)

        return compiled_pattern.finditer(buffer_view, *self._find_args[0], **self._find_args[1])


if __name__ == "__main__":
    # ==== Test the VectorRegexSearch ====
    text = b"hello world, hello numpy! regex is fast on pure vectors."
    buffer = np.frombuffer(text, dtype=np.uint8)
    print(buffer)

    # Instantiate the searcher
    searcher = VectorRegexSearch(backend='regex')

    print("--- Test 1: String Pattern ---")
    # Testing standard string pattern
    for match in searcher("hello", buffer):
        print(f"Found 'hello' at span: {match.span()} - Bytes: {match.group()}")

    print("\n--- Test 2: Bytes Pattern (with Regex) ---")
    # Testing bytes pattern with regex characters
    for match in searcher(b"re[a-z]+", buffer):
        print(f"Found regex match at span: {match.span()} - Bytes: {match.group()}")

    print("\n--- Test 3: Numpy Array Pattern ---")
    # Testing passing a numpy array directly as the pattern
    pattern_arr = np.frombuffer(b"pure", dtype=np.uint8)
    for match in searcher(pattern_arr, buffer):
        print(f"Found 'pure' from array pattern at span: {match.span()} - Bytes: {match.group()}")
