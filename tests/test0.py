from sys import maxunicode
from sys import maxunicode

PRINTABLE_CHARS = [
    c for c in map(chr, range(33, maxunicode + 1))
    if c.isprintable() and not c.isspace()
]

for i, char in enumerate(PRINTABLE_CHARS):
    print(i, char)
    if i > 256:
        break
