from typing import Callable, Any
from inspect import signature


class Signal[*T]:
    """Implements a QT-like signal system for interactive programming.

    For convenience, the emitter does not force the connected callable to take all the arguments that are emitted.
    Thus, even if the emitter includes 2 arguments, but the callee only expects 1 or 0, the *args will be truncated.
    If, however, there are more than the expected number of arguments, an error will occur as expected.

    Please note that any connected functions/methods will result in them (or their objects because methods are bound
    and thus ephemeral) staying ALIVE in memory until disconnected, so make sure to disconnect any methods before
    deleting an object.

    If you want to implement signals globally, define them on the class space. Conversely, if you want signals to
    be tied to a certain classes instances, define them as attributes. It may be useful to do both, hence you would
    prefix or suffix the signal names when defining them in both the instance and class spaces. Alternatively, you
    could also pass `self` when emitting and let the client decide what to do based on that.
    """
    __slots__ = ('callables',)

    def __init__(self) -> None:
        self.callables: list[tuple[Callable[[*T], Any], int]] = []

    @property
    def callables_count(self) -> int:
        return len(self.callables)

    def emit(self, *args: *T) -> None:
        for c, arg_len in self.callables:
            c(*args[:arg_len])

    def connect(self, c: Callable[..., Any]) -> None:
        if c not in self.callables:
            self.callables.append((c, len(signature(c).parameters)))

    def disconnect(self, c: Callable[..., Any]) -> None:
        matches: list[int] = [i for i, (c_, _) in enumerate(self.callables) if c_ is c]
        for i in reversed(matches):
            self.callables.pop(i)


if __name__ == "__main__":
    t: Signal[str, str] = Signal()
    t1: Signal = Signal()
    t1.emit()  # highlighting bug...
    f1 = lambda a, b: print(a)
    f2 = lambda a, b, c: print(a, b)
    t.connect(f1)
    t.connect(f2)
    t.emit("yup", "")
