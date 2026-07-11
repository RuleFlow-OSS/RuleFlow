# for i in range(256):
#     print(i, chr(i))
from typing import NamedTuple

class T(NamedTuple):
    a: int
    b: int
    c: set = set()

t = T(1, 2)
t.c.add(3)
print(t)

a = T(4, 5)
print(a)
