# import numpy as np
# from typing import Union, Sequence
from sys import maxunicode
from wcwidth import wcwidth

# Character Set Setup
PRINTABLE_CHARS = [
    c for c in map(chr, range(33, maxunicode + 1))
    if c.isprintable() and not c.isspace() and wcwidth(c) == 1
]
ASCII = PRINTABLE_CHARS[:94]
del PRINTABLE_CHARS[:94]
PRINTABLE_CHARS[33:33] = ASCII

# Pre-compute reverse lookup dictionary for O(1) access in ord_rff
# _CHAR_TO_INT = {c: i for i, c in enumerate(PRINTABLE_CHARS)}
_RFF_LEN = len(PRINTABLE_CHARS)


def chr_rff(o: int) -> str:
    try:
        return PRINTABLE_CHARS[int(o)]
    except IndexError:
        return PRINTABLE_CHARS[int(o) % _RFF_LEN]


# NOTE: not currently using the following code. It may, however, be useful at some point in the future.
# def ord_rff(c: str) -> int:
#     """
#     Returns the integer index of a character in the RFF character set.
#     """
#     if len(c) != 1:
#         raise TypeError(f"ord_rff() expected a character, but string of length {len(c)} found")
#
#     try:
#         return _CHAR_TO_INT[c]
#     except KeyError:
#         raise ValueError(f"Character {c!r} is not in the RFF printable character set.")
#
#
# def encode(data: Union[bytes, str, Sequence[int], np.ndarray]) -> np.ndarray:
#     """
#     Converts various data types into a NumPy array of RFF integer indices.
#     - Strings are parsed through ord_rff().
#     - Bytes use fast memory-mapping via np.frombuffer.
#     - Sequences are cast to np.int32 arrays.
#     """
#     if isinstance(data, str):
#         return np.array([ord_rff(char) for char in data], dtype=np.int32)
#     elif isinstance(data, (bytes, bytearray)):
#         # Highly efficient byte-to-numpy conversion
#         return np.frombuffer(data, dtype=np.uint8).astype(np.int32)
#     else:
#         # Handles Sequence[int] or existing np.ndarray
#         return np.asarray(data, dtype=np.int32)
#
#
# def decode(data: Union[Sequence[int], np.ndarray], as_bytes: bool = False) -> Union[str, bytes]:
#     """
#     Translates a sequence or NumPy array of integers back into a string or bytes.
#     """
#     if as_bytes:
#         # If it's a numpy array, we can use fast casting and tobytes()
#         if isinstance(data, np.ndarray):
#             if np.any((data < 0) | (data > 255)):
#                 raise ValueError("Array contains integers outside 0-255 range and cannot be decoded to bytes.")
#             return data.astype(np.uint8).tobytes()
#
#         # Fallback for standard sequences
#         try:
#             return bytes(data)
#         except ValueError:
#             raise ValueError("Sequence contains integers outside 0-255 range and cannot be decoded to bytes.")
#
#     # Using a generator with .item() is faster for NumPy scalars
#     if isinstance(data, np.ndarray):
#         return "".join(chr_rff(i.item()) for i in data)
#
#     return "".join(chr_rff(i) for i in data)


if __name__ == "__main__":
    pass
