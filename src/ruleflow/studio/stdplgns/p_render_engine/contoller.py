from ruleflow.studio.stdplgns.p_render_engine.client_side import (
    IpAddressSqidsEncoding, Config, Client, cast_none
)
from ruleflow.studio.stdplgns.p_render_engine.message_channels import ChannelWriter
from ruleflow.studio.stdplgns.p_render_engine.message_protocol import *
from ruleflow.core.signals import Signal
from typing import Literal
from asyncio import Task
import asyncio


class ClientController:
    """
    We have a separate controller due closely following the Server side design on the Client side.
    This design enables us to scale up as we develop the protocol.
    """

    loopback_sqid_code: str = IpAddressSqidsEncoding.encode(Config.loopback_address)

    def __init__(self):
        self.client: Client = Client()
        self.channel_writer: ChannelWriter[Message] = self.client.message_channels.get_outgoing_writer()
        self.client_task: asyncio.Task = cast_none(Task)
        self.current_ip_address: str = Config.loopback_address
        self.on_command_message_received: Signal[CommandMessage] = Signal()
        self.on_ping_pong_received: Signal[CommandMessage] = Signal()

    def connect(self, sqid_code: str):
        ip_address: str = IpAddressSqidsEncoding.decode(sqid_code)
        self.current_ip_address = ip_address
        self.client.connect(ip_address)
        self.client_task = asyncio.create_task(self._message_handler())

    def disconnect(self):
        self.client.disconnect()
        try: self.client_task.cancel()
        except asyncio.CancelledError: pass

    async def _message_handler(self) -> None:
        """
        Main loop for processing all incoming messages. Always running.
        """
        channel_reader = self.client.message_channels.get_incoming_reader()
        async for msg in channel_reader.read_all():
            if not isinstance(msg, CommandMessage):
                continue  # only handle command messages
            match msg.Op:
                case "ping":
                    self.ping_server(op="pong")
                    self.on_ping_pong_received.emit(msg)
                case "pong":
                    self.on_ping_pong_received.emit(msg)
                case _:
                    self.on_command_message_received.emit(msg)

    def ping_server(self, op: Literal["ping", "pong"] = "ping", args: str = "Client Says Hi!"):
        """Ping the server."""
        self.send_message(CommandMessage(Op=op, Args=args))

    def send_message(self, msg: Message) -> bool:
        """Use this to send a message to the server (thread-safe)."""
        return self.channel_writer.try_write(msg)


if __name__ == '__main__':
    # ==== Test Connection ====
    async def main():
        ctrl = ClientController()
        ctrl.on_ping_pong_received.connect(lambda m: print(f"Received: {m}"))
        ctrl.client.on_connected.connect(lambda: ctrl.ping_server())

        ctrl.connect(ClientController.loopback_sqid_code)
        await asyncio.sleep(2.0)  # Give it 2 seconds to connect, send, and receive
        ctrl.disconnect()
        await asyncio.sleep(0.1)  # Let tasks finish cleanup

    asyncio.run(main())
