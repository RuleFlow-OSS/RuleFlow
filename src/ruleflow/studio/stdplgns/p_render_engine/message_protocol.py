"""
CRITICAL: This protocol must be kept in sync with the server side implementation.
"""
from pydantic import BaseModel, Field, TypeAdapter
from typing import Annotated, Literal, Union, cast
from abc import ABC


class Message(BaseModel, ABC):
    """Message is an ABC that supports polymorphic JSON serialization."""

    @staticmethod
    def from_bytes(data: bytes) -> AnyMessage:
        return _message_adapter.validate_json(data)

    def to_bytes(self) -> bytes:
        return self.model_dump_json().encode("utf-8")


class EventMessage(Message):
    """An EventMessage is for RuleFlow event data."""
    Type: Literal["event"] = "event"
    Idx: int = 0
    DistanceToCreation: int = 0
    Connected: tuple[int, ...] = Field(default_factory=tuple[int, ...])  # this must be in the form tuple[int, ...] to avoid crazy crashes.
    Data: tuple[int, ...] = Field(default_factory=tuple[int, ...])


class CommandMessage(Message):
    """A CommandMessage is for controller logic."""
    Type: Literal["command"] = "command"
    Op: str = ""
    Args: str = ""
    Kwargs: str = ""


# TypeAdapter handles polymorphic dispatch using the "type" field
AnyMessage = Annotated[
    Union[EventMessage, CommandMessage],
    Field(discriminator="Type")
]
_message_adapter = TypeAdapter(AnyMessage)


if __name__ == '__main__':
    m: CommandMessage = cast(CommandMessage, Message.from_bytes(b"""{"Type": "command", "Op": "test", "Args": "test", "Kwargs": "test"}"""))
    print(m.Op)
    m1 = CommandMessage(Op="test1", Args="test2")
    print(m1.to_bytes())
