from ruleflow.studio.stdplgns.p_render_engine.message_channels import (
    MessageChannels, ChannelReader, ChannelWriter
)
from ruleflow.studio.stdplgns.p_render_engine.message_protocol import Message
from ruleflow.core.signals import Signal
from asyncio import StreamReader, StreamWriter, Task
from typing import Any
from sqids import Sqids
import asyncio
import struct
import json


def cast_none[T](_type: type[T]) -> T:
    return None


class Config:
    """
    Configuration of Client/Server communication and setup.
    IMPORTANT: This class must be kept up to date with the server side configuration.
    """
    loopback_address: str = '127.0.0.1'  # localhost
    port: int = 31415
    max_message_length: int = 10485760  # 10 * 1024 * 1024 = 10485760 (that is 10MB)
    max_message_channel_size: int = 2048
    sqids_config: dict[str, Any] = (lambda **kw: kw)(
        alphabet='123456789ABCDEFGHIJKLMNPQRSTUVWXYZ'
    )


class IpAddressSqidsEncoding:
    sqids: Sqids = Sqids(**Config.sqids_config)

    @classmethod
    def encode(cls, ip_address: str) -> str:
        """Takes an IP address and encodes it into the sqids string."""
        parts: bytes = bytes(int(p) for p in ip_address.split('.'))
        n: int = int.from_bytes(parts, byteorder='big')
        return cls.sqids.encode((n,))

    @classmethod
    def decode(cls, sqids_code: str) -> str:
        """Takes a sqids string decodes it into an IP address."""
        try:
            n: int = cls.sqids.decode(sqids_code)[0]
            parts: bytes = n.to_bytes(4, byteorder='big')
            return '.'.join(str(p) for p in parts)
        except Exception as e:
            raise ValueError("Invalid sqids code") from e


class Client:
    def __init__(self):
        # Fired when a connected was attempted, but failed.
        self.on_connection_failed: Signal = Signal()
        # Fired immediately when connected to the server and streams are ready.
        self.on_connected: Signal = Signal()
        # Fired when an active connection ends and cleanup is complete.
        self.on_disconnected: Signal = Signal()
        # Fired whenever the FSM completely exits (whether from waiting or connected state).
        self.on_stopped: Signal = Signal()

        self.awake: bool = False  # True when the FSM is active.
        self.connected: bool = False  # Tells us if we are connected.
        self.client_task: Task = cast_none(Task)  # used to manage the task
        self.stream_writer: StreamWriter = cast_none(StreamWriter)
        self.stream_reader: StreamReader = cast_none(StreamReader)
        self.message_channels: MessageChannels = MessageChannels(Config.max_message_channel_size)

    def connect(self, ip_address: str) -> None:
        if self.awake:
            return
        self.awake = True
        # self.message_channels.get_outgoing_writer().bind_loop(asyncio.get_running_loop())  # this is to provide thread safety
        self.client_task = asyncio.create_task(
            self._waiting_for_connection_state(ip_address)
        )

    def disconnect(self) -> None:
        if self.awake:
            self.client_task.cancel()

    # ======== FSM States (primary transition code is defined within state) ========
    async def _waiting_for_connection_state(self, ip_address: str) -> None:
        try:
            self.stream_reader, self.stream_writer = await asyncio.open_connection(
                ip_address, Config.port,
                limit=Config.max_message_length
            )
        except (asyncio.CancelledError, Exception) as e:
            if self.stream_writer:
                self.stream_writer.close()
            self.awake = False
            self.on_stopped.emit()
            if not isinstance(e, asyncio.CancelledError):
                self.on_connection_failed.emit()
            return

        # Transition into connected state
        incoming_data: Task = asyncio.create_task(self._process_incoming_channel())
        outgoing_data: Task = asyncio.create_task(self._connected_state())
        try:
            self.connected = True
            self.on_connected.emit()
            await asyncio.wait(
                {outgoing_data, incoming_data},
                return_when=asyncio.FIRST_COMPLETED
            )
        except asyncio.CancelledError:
            pass  # Because we aren't using something CancellationToken, we must hand this exception everywhere.
        finally:  # all exceptions must be handled by transitions
            # Cancel both child tasks and wait for them to exit cleanly (mirrors Cts.CancelAsync + Task.WhenAll)
            outgoing_data.cancel()
            incoming_data.cancel()
            await asyncio.gather(outgoing_data, incoming_data, return_exceptions=True)
            self.stream_writer.close()
            try:
                await self.stream_writer.wait_closed()
            except (Exception, asyncio.CancelledError):  # could be due to cancellation or anything... better to be robust than sorry.
                pass
            self.message_channels.drain()
            self.connected = False
            self.awake = False
            self.on_disconnected.emit()
            self.on_stopped.emit()

    async def _connected_state(self) -> None:
        try:
            channel_reader: ChannelReader[Message] = self.message_channels.get_outgoing_reader()
            stream_writer: StreamWriter = self.stream_writer
            async for message in channel_reader.read_all():
                try: message_bytes: bytes = message.to_bytes()
                except: continue
                buffer: bytes = struct.pack(">i", len(message_bytes)) + message_bytes
                stream_writer.write(buffer)
                await stream_writer.drain()
        except (Exception, asyncio.CancelledError):
            pass  # asyncio.CancelledError equivalent to OperationCanceledException in C#

    async def _process_incoming_channel(self) -> None:
        channel_writer: ChannelWriter[Message] = self.message_channels.get_incoming_writer()
        stream_reader: StreamReader = self.stream_reader
        try:
            while True:
                length_buffer = await stream_reader.readexactly(4)
                (message_length,) = struct.unpack(">i", length_buffer)
                if message_length <= 0 or message_length > Config.max_message_length:
                    break
                message_buffer = await stream_reader.readexactly(message_length)
                try:
                    msg = Message.from_bytes(message_buffer)
                    if msg is not None:
                        await channel_writer.write(msg)
                except (json.JSONDecodeError, ValueError, KeyError, TypeError):
                    continue
        # All errors regarding the reading buffer must break the loop because we lose position.
        except (asyncio.IncompleteReadError, asyncio.CancelledError, Exception):
            # IncompleteReadError is equivalent to EndOfStreamException in C#
            # CancelledError is equivalent to OperationCanceledException in C#
            pass


if __name__ == '__main__':
    pass
    # ==== Test sqids Code ====
    # c = IpAddressSqidsEncoding.encode('10.26.26.213')
    # print(c)
    # print(IpAddressSqidsEncoding.decode(c))

    # ==== Test Connection ====
    from message_protocol import CommandMessage
    async def main() -> None:
        client = Client()
        writer = client.message_channels.get_outgoing_writer()
        reader = client.message_channels.get_incoming_reader()

        client.connect("127.0.0.1")
        print("Waiting for connection...")

        while not client.connected:
            if not client.awake:
                print("Connection failed! Is the C# server running?")
                return
            await asyncio.sleep(0.05)  # Yield to the event loop for 50ms

        print("Connected! Sending test message...")
        test_msg = CommandMessage(Op="test_ping", Args="hello", Kwargs="{}")
        await writer.write(test_msg)
        await asyncio.sleep(1.0)
        reply = reader.try_read()
        if reply:
            print(f"Received from server: {reply}")
        input("Press any key to exit...")
        print("Disconnecting...")
        client.disconnect()
        await client.client_task
        print("Test complete.")
    asyncio.run(main())
