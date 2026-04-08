"""
Some helpers to represent numbers in flow lang. Specifically, we add support for integer infinities and helpful
functions to convert strings to numbers appropriately.
"""
from sys import maxsize


class Inf(int):
    """Represents positive infinity (+inf)."""

    def __new__(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = super().__new__(cls, maxsize)
        # noinspection PyUnresolvedReferences
        return cls._instance

    def __repr__(self):
        return 'inf'

    def __str__(self):
        return 'inf'

    def __float__(self):
        return float('inf')

    # Comparison
    def __eq__(self, other):
        return other is self

    def __gt__(self, other):
        return other is not self

    def __lt__(self, other):
        return False

    def __ge__(self, other):
        return True

    def __le__(self, other):
        return other is self

    # Arithmetic
    def __add__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __sub__(self, other):
        # inf - x = inf (unless x is inf)
        if other is NEG_INF:
            return self  # inf - (-inf) = inf + inf = inf
        elif other is INF:
            raise ValueError("inf - inf is undefined")  # Or return float('nan')
        return self

    def __rsub__(self, other):
        # x - inf = -inf
        return NEG_INF

    def __mul__(self, other):
        if other == 0:
            return 0
        elif other > 0 or other is INF:
            return self
        else:  # other < 0 or other is NEG_INF
            return NEG_INF

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if other == 0 or other is self or other is NEG_INF:
            raise ZeroDivisionError("division by zero or infinity/infinity")
        return float('inf') if other > 0 else -float('inf')

    def __rtruediv__(self, other):
        # x / inf = 0
        return 0.0

    def __neg__(self):
        # -inf = -inf
        return NEG_INF
INF = Inf()


class NegInf(int):
    """Represents negative infinity (-inf)."""

    def __new__(cls):
        if not hasattr(cls, '_instance'):
            cls._instance = super().__new__(cls, -maxsize)
        # noinspection PyUnresolvedReferences
        return cls._instance

    def __repr__(self):
        return '-inf'

    def __str__(self):
        return '-inf'

    def __float__(self):
        return float('-inf')

    # Comparison
    def __eq__(self, other):
        return other is self

    def __gt__(self, other):
        return False

    def __lt__(self, other):
        return other is not self

    def __ge__(self, other):
        return other is self

    def __le__(self, other):
        return True

    # Arithmetic
    def __add__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __sub__(self, other):
        # -inf - x = -inf
        if other is NEG_INF:
            raise ValueError("-inf - (-inf) is undefined")  # Or return float('nan')
        return self

    def __rsub__(self, other):
        # x - (-inf) = x + inf = inf
        return INF

    def __mul__(self, other):
        if other == 0:
            return 0
        elif other > 0 or other is INF:
            return self  # -inf * positive = -inf
        else:  # other < 0 or other is NEG_INF
            return INF  # -inf * negative = inf

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if other == 0 or other is INF or other is NEG_INF:
            raise ZeroDivisionError("division by zero or infinity/infinity")
        return float('-inf') if other > 0 else float('inf')

    def __rtruediv__(self, other):
        # x / -inf = 0
        return 0.0

    def __neg__(self):
        # -(-inf) = inf
        return INF
NEG_INF = NegInf()


def str_to_num(num: str) -> int | float:
    """
    >>> str_to_num('1')
    1
    >>> str_to_num('1.2')
    1.2
    >>> str_to_num('inf')
    inf
    >>> str_to_num('-inf')
    -inf
    """
    if num == 'inf':
        return INF
    elif num == '-inf':
        return NEG_INF
    try:
        return int(num)
    except ValueError:
        return float(num)


def is_infinity(num: int | Inf) -> bool:
    return isinstance(num, Inf)


if __name__ == '__main__':
    a = [1, 2, 3]
    print(a[-INF:1])
