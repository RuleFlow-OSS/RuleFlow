"""
I implemented a light abstraction over asyncio's Queue to be loosely
patterned after C#'s producer-consumer Channel conduit.
"""
from ruleflow.studio.stdplgns.p_render_engine.message_protocol import Message
from asyncio import Queue, QueueEmpty, QueueFull
from typing import AsyncIterator


class ChannelReader[T]:
    """Patterned after C#'s ChannelReader<T>."""
    def __init__(self, queue: Queue[T]):
        self._queue = queue

    async def read(self) -> T:
        return await self._queue.get()

    async def read_all(self) -> AsyncIterator[T]:
        """Equivalent to C#'s ChannelReader.ReadAllAsync()."""
        while True:
            yield await self._queue.get()

    def try_read(self) -> T | None:
        try:
            return self._queue.get_nowait()
        except QueueEmpty:
            return None


class ChannelWriter[T]:
    def __init__(self, queue: Queue[T]):
        self._queue = queue

    def try_write(self, item: T) -> bool:
        try:
            self._queue.put_nowait(item)
            return True
        except QueueFull:
            return False

    async def write(self, item: T) -> None:
        await self._queue.put(item)


class MessageChannels:
    def __init__(self, max_size: int):
        # Incoming messages stored in the order they are received
        self.incoming_channel: Queue[Message] = Queue(maxsize=max_size)
        # Outgoing messages sent in the order they are enqueued
        self.outgoing_channel: Queue[Message] = Queue(maxsize=max_size)

        self._incoming_reader = ChannelReader[Message](self.incoming_channel)
        self._incoming_writer = ChannelWriter[Message](self.incoming_channel)
        self._outgoing_reader = ChannelReader[Message](self.outgoing_channel)
        self._outgoing_writer = ChannelWriter[Message](self.outgoing_channel)

    def get_incoming_reader(self) -> ChannelReader[Message]:
        return self._incoming_reader

    def get_incoming_writer(self) -> ChannelWriter[Message]:
        return self._incoming_writer

    def get_outgoing_reader(self) -> ChannelReader[Message]:
        return self._outgoing_reader

    def get_outgoing_writer(self) -> ChannelWriter[Message]:
        return self._outgoing_writer

    def drain(self) -> None:
        """Use this to clear any remaining messages."""
        while self._incoming_reader.try_read() is not None:
            pass
        while self._outgoing_reader.try_read() is not None:
            pass
