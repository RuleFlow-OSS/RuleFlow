"""
This plugin provides basic executing/undoing features, hot-reload, and several other utilities for interactive flows.
"""
# Textual Imports
from textual.widgets import Collapsible, TabPane, Input, Button, Checkbox, RadioSet, RadioButton, Label, RichLog
from textual.widget import Widget
from textual import events
from textual.containers import ScrollableContainer, HorizontalGroup

# Standard Imports
from typing import Iterator
from ruleflow.studio.model import Plugin
from ruleflow.lang.interpreter import FlowLang

# Peer Imports
from ruleflow.studio.stdplgns.p_render_engine.contoller import ClientController, Config
from ruleflow.studio.stdplgns.p_render_engine.message_protocol import *


# noinspection DuplicatedCode
class P(Plugin):
    name = 'RenderEngine'
    file_types = ['.flow', '.pflow', '.wpflow']

    @property
    def flow(self) -> FlowLang:
        return self.model.data.setdefault('flow', FlowLang())

    def on_initialized(self) -> None:
        # ==== Client Side ====
        self.ctrl: ClientController = ClientController()
        self.ctrl.client.on_stopped.connect(self.on_client_stopped)
        self.ctrl.client.on_connected.connect(self.on_connected)
        self.ctrl.client.on_disconnected.connect(self.on_disconnected)
        self.ctrl.on_ping_pong_received.connect(
            lambda msg:  self.log_view.write(f"Rcvd> [bold green]{msg.Op}: {msg.Args}[/]")
        )
        self.ctrl.client.on_connection_failed.connect(
            lambda: self.log_view.write("> [bold red]Connection Failed[/]")
        )

        # ==== Plugin Side ====
        self.view.sig_button_pressed.connect(
            self.handle_btn_press
        )

    def on_client_stopped(self):
        self.log_view.write("> [bold #FFA500]Client Stopped[/]")
        self.set_connected_ui_state(False)

    def on_connected(self):
        self.log_view.write(f"[bold green] ---- Connected ---- [/]")
        self.set_connected_ui_state(True)
        self.flow.on_evolved_n.connect(self.handle_flow_evolve)
        self.flow.on_regress_n.connect(self.handle_flow_regress)
        self.flow.on_clear.connect(self.handle_flow_clear)
        # TODO: investigate why errors are not being propagated up (it just drops the connection if an error happens in
        #  the connected callback... i.e. if we put an error here like ValueError, it drops the connection.)

    def on_disconnected(self):
        self.log_view.write(f"> [bold #FFA500]Disconnected[/]")
        self.flow.on_evolved_n.disconnect(self.handle_flow_evolve)
        self.flow.on_regress_n.disconnect(self.handle_flow_regress)
        self.flow.on_clear.disconnect(self.handle_flow_clear)

    def handle_flow_evolve(self, n: int):
        if not self.event_streaming_enabled.value:
            return
        for e in self.flow.events[-n:]:
            self.ctrl.send_message(
                EventMessage(
                    Idx=e.time,
                    DistanceToCreation=e.causal_distance_to_creation,
                    Connected=tuple[int](e.causally_connected_events)
                )
            )

    def handle_flow_regress(self, n: int):
        if not self.event_streaming_enabled.value:
            return
        self.ctrl.send_message(CommandMessage(Op='regress', Args=str(n)))

    def handle_flow_clear(self):
        if not self.event_streaming_enabled.value:
            return
        self.ctrl.send_message(CommandMessage(Op='clear'))

    def controls(self) -> Iterator[Widget]:
        self.connection_code = Input(
            value=self.ctrl.loopback_sqids_code,
            placeholder=f'e.g. {self.ctrl.loopback_sqids_code}',
            restrict=f'[{Config.sqids_config['alphabet']}]*'
        )
        self.connection_code.border_title = 'Connection Code'
        yield self.connection_code
        with HorizontalGroup():
            self.connect_btn = Button('Connect', id='re-connect')
            yield self.connect_btn
            self.disconnect_btn = Button('Stop', id='re-disconnect')
            self.disconnect_btn.display = False
            yield self.disconnect_btn
            yield Label(' ')
            self.test_connection_btn = Button('Ping', id='re-ping')
            self.test_connection_btn.disabled = True
            yield self.test_connection_btn

        self.event_streaming_enabled = Checkbox("Event Streaming", value=True)
        self.event_streaming_enabled.display = False
        yield self.event_streaming_enabled

        yield Label()

    def panel(self) -> TabPane | None:
        self.log_view = RichLog(highlight=True, markup=True, wrap=True)
        return TabPane(
            self.name,
            ScrollableContainer(
                self.log_view,
                Button('Clear Log', id='re-clear-log'),
                Label(),
            )
        )

    def set_connected_ui_state(self, b: bool, only_connection_elements: bool = False) -> None:
        self.disconnect_btn.display = b
        self.connect_btn.display = not b
        self.connection_code.disabled = b
        if only_connection_elements:
            return
        self.test_connection_btn.disabled = not b
        self.event_streaming_enabled.display = b

    def handle_btn_press(self, e: Button.Pressed):
        match e.button.id:
            case 're-connect':
                try:
                    self.ctrl.connect(self.connection_code.value)
                    self.set_connected_ui_state(True, only_connection_elements=True)
                    self.log_view.write(
                        f"> [bold #FFA500]Attempting {self.ctrl.current_ip_address} on port {Config.port}[/]"
                    )
                except ValueError:
                    self.view.notify(
                        'Please enter well-formed connection code!',
                        title='Bad Connection Code', severity='error'
                    )
            case 're-disconnect':
                self.ctrl.disconnect()
                self.set_connected_ui_state(False)
            case 're-ping':
                self.log_view.write(f"Sent> ping")
                self.ctrl.ping_server()
            case 're-clear-log':
                self.log_view.clear()
                self.log_view.write(f"[bold green] --- Log Cleared --- [/]")
