"""
This plugin provides auditory exploration of cellular systems using the SCAMP library.
It translates spatial cell configurations into musical chords and arpeggios, and allows
for sheet music transcription.

Note: https://www.soundslice.com/ is an excellent site for playing back the generated xml files.
"""
# Textual Imports
from textual.widgets import (Collapsible, TabPane, Input, Select,
                             Checkbox, Button, Label, RichLog)
from textual.widget import Widget
from textual.containers import VerticalScroll, HorizontalGroup

# Standard Imports
from typing import Iterator
import threading
from studio.model import Plugin
from lang.interpreter import FlowLang

# Attempt to import SCAMP. If it fails, we flag it so the UI can warn the user.
try:
    import scamp
    SCAMP_AVAILABLE = True
except ImportError:
    SCAMP_AVAILABLE = False


# ==== Musical Scales & Progressions ====
SCALES = {
    "C Pentatonic Major (Bright)": [0, 2, 4, 7, 9],
    "A Aeolian Minor (Melancholic)": [0, 2, 3, 5, 7, 8, 10],
    "F Lydian (Dreamy)": [0, 2, 4, 6, 7, 9, 11],
    "D Harmonic Minor (Classical)": [0, 2, 3, 5, 7, 8, 11],
    "Whole Tone (Ethereal)": [0, 2, 4, 6, 8, 10]
}


def get_extended_scale(scale_intervals: list[int], octaves: int = 5, base_midi: int = 48) -> list[int]:
    """Extends a set of scale intervals across multiple octaves."""
    pitches = []
    for oct in range(octaves):
        for interval in scale_intervals:
            pitches.append(base_midi + (oct * 12) + interval)
    return pitches


class P(Plugin):
    name = 'Tunes'
    file_types = ['.flow']

    @property
    def flow(self) -> FlowLang:
        return self.model.data.setdefault('flow', FlowLang())

    def on_initialized(self) -> None:
        # Internal State
        self._is_playing: bool = False
        self._playback_thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()

        # Connect UI Signals
        self.view.sig_button_pressed.connect(self._handle_button_press)

    def controls(self) -> Iterator[Widget]:
        with Collapsible(title='Playback Controls', collapsed=False):
            with HorizontalGroup():
                yield Button('▶ Play', id='btn-play-music', variant="success")
                yield Button('■ Stop', id='btn-stop-music', variant="error")

            yield Label("\nTempo (BPM)")
            self.bpm_input = Input(value='120', placeholder='e.g. 120')
            yield self.bpm_input

            yield Label("Playback Timing")
            self.timing_select = Select(
                [("Sequential (Arpeggio)", "seq"), ("Simultaneous (Chord)", "chord")],
                value="seq", allow_blank=False
            )
            yield self.timing_select

        with Collapsible(title='Musical Mapping', collapsed=False):
            yield Label("Base Instrument")
            self.base_instrument_select = Select(
                [
                    ("Piano", "piano"), ("Marimba", "marimba"),
                    ("Vibraphone", "vibraphone"), ("Cello", "cello"),
                    ("Harp", "harp"), ("Glockenspiel", "glockenspiel"),
                    ("Standard Drumkit", "drumkit:standard"),
                    ("Electronic Drumkit", "drumkit:electronic"),
                    ("808 Drumkit", "drumkit:808"),
                    ("Jazz Drumkit", "drumkit:jazz"),
                    ("Orchestra Drumkit", "drumkit:orchestra"),
                    ("Woodblock", "woodblock")
                ],
                value="piano", allow_blank=False
            )
            yield self.base_instrument_select

            yield Label("Instrument Map (Quanta: Instr)")
            self.instrument_map_input = Input(value='', placeholder='e.g. A: drumkit:808, B: cello')
            yield self.instrument_map_input

            yield Label("Pitch Mapping Mode")
            self.mapping_mode = Select(
                [
                    ("Position + Quanta Combined", "combined"),
                    ("Quanta Value Only", "quanta"),
                    ("Spatial Position Only", "position")
                ],
                value="combined", allow_blank=False
            )
            yield self.mapping_mode

            yield Label("Ignored Quanta (Comma Separated)")
            self.ignored_input = Input(value='.,0,_', placeholder='e.g. .,0,_')
            yield self.ignored_input

        with Collapsible(title='Scale & Tuning Config', collapsed=True):
            yield Label("Scale / Progression")
            self.scale_select = Select(
                [(name, name) for name in SCALES.keys()] + [("Custom (Use Intervals Below)", "custom")],
                value="C Pentatonic Major (Bright)", allow_blank=False
            )
            yield self.scale_select

            yield Label("Custom Intervals (Comma Separated)")
            self.custom_scale_input = Input(value='0, 2, 4, 7, 9', placeholder='e.g. 0, 2, 4, 7, 9')
            yield self.custom_scale_input

            yield Label("Number of Octaves")
            self.octaves_input = Input(value='5', placeholder='e.g. 5')
            yield self.octaves_input

            yield Label("Base MIDI Note (C3 = 48)")
            self.base_midi_input = Input(value='48', placeholder='e.g. 48')
            yield self.base_midi_input

        with Collapsible(title='Transcription & Export', collapsed=False):
            self.export_checkbox = Checkbox('Record Performance', value=False)
            yield self.export_checkbox

            self.export_format = Select(
                [("MusicXML (.xml)", "xml"), ("MIDI (.mid)", "mid")],
                value="xml", allow_blank=False
            )
            yield self.export_format

    def panel(self) -> TabPane | None:
        self.log_view = RichLog(id="tunes-log-view", highlight=True, markup=True, wrap=True)
        return TabPane(
            self.name.title(),
            VerticalScroll(
                self.log_view
            )
        )

    def _handle_button_press(self, event: Button.Pressed) -> None:
        if event.button.id == 'btn-play-music':
            self._start_playback()
        elif event.button.id == 'btn-stop-music':
            self._stop_playback()

    def _start_playback(self) -> None:
        if not SCAMP_AVAILABLE:
            self.log_view.write("[bold red]SCAMP library not found![/bold red]")
            self.log_view.write("Please run `pip install scamp` in your environment to use this plugin.")
            return

        if self._is_playing:
            self.view.notify("Music is already playing.", severity="warning")
            return

        if not self.flow.events:
            self.log_view.write("[bold red]No simulation events found. Run the engine first.[/bold red]")
            return

        try:
            float(self.bpm_input.value)
        except ValueError:
            self.view.notify("Invalid BPM value.", severity="error")
            return

        self.log_view.clear()
        self._is_playing = True
        self._stop_event.clear()

        # Use native python threading to allow immediate interruption via threading.Event
        self._playback_thread = threading.Thread(target=self._playback_loop, daemon=True)
        self._playback_thread.start()

    def _stop_playback(self) -> None:
        # Executes directly in UI thread. No self.cft() necessary.
        if self._is_playing:
            self.log_view.write("[bold yellow]Stopping playback gracefully...[/bold yellow]")
            self._stop_event.set()

    def _wait_interruptable(self, session: 'scamp.Session', duration: float) -> bool:
        """
        Blocks the SCAMP clock in small increments so that the stop event can interrupt
        long musical rests or notes immediately without freezing the application thread.
        Returns False if interrupted.
        """
        waited = 0.0
        step = 0.1
        while waited < duration:
            if self._stop_event.is_set():
                return False
            wait_time = min(step, duration - waited)
            session.wait(wait_time)
            waited += wait_time
        return True

    def _playback_loop(self) -> None:
        """The main blocking thread loop that processes the cellular flow and plays audio."""
        session = None
        try:
            bpm = float(self.bpm_input.value)
            base_instrument_name = self.base_instrument_select.value
            scale_name = self.scale_select.value
            playback_timing = self.timing_select.value
            mapping_mode = self.mapping_mode.value
            ignored_chars = [c.strip() for c in self.ignored_input.value.split(',')]

            # Parse Instrument Map
            instr_map = {}
            if self.instrument_map_input.value.strip():
                pairs = self.instrument_map_input.value.split(',')
                for pair in pairs:
                    if ':' in pair:
                        q, instr = pair.split(':', 1)
                        instr_map[q.strip()] = instr.strip()

            # Setup SCAMP Session
            session = scamp.Session(tempo=bpm)

            # Preload parts to avoid stutter during mid-playback instantiation
            parts = {}
            def get_part(name: str):
                name_lower = name.lower()
                is_drum = name_lower.startswith("drumkit") or name_lower in ("percussion", "drums")

                if is_drum:
                    # Determine General MIDI drumkit preset based on the tag
                    preset_num = 0  # Default to Standard Kit
                    if "electronic" in name_lower:
                        preset_num = 24
                    elif "808" in name_lower:
                        preset_num = 25
                    elif "jazz" in name_lower:
                        preset_num = 32
                    elif "orchestra" in name_lower:
                        preset_num = 48

                    # Cache key needs to be unique per kit type
                    actual_name = f"Drums_{preset_num}"
                    if actual_name not in parts:
                        # Map to General MIDI Bank 128 (Percussion) with the specified Preset
                        parts[actual_name] = session.new_part("Drums", preset=(128, preset_num))
                    return parts[actual_name]
                else:
                    if name not in parts:
                        parts[name] = session.new_part(name)
                    return parts[name]

            get_part(base_instrument_name)
            for instr_name in instr_map.values():
                get_part(instr_name)

            # Parse Tuning Parameters
            try:
                octaves = int(self.octaves_input.value)
            except ValueError:
                octaves = 5

            try:
                base_midi = int(self.base_midi_input.value)
            except ValueError:
                base_midi = 48

            if scale_name == "custom":
                try:
                    intervals = [int(x.strip()) for x in self.custom_scale_input.value.split(',')]
                except ValueError:
                    intervals = SCALES["C Pentatonic Major (Bright)"]  # fallback
            else:
                intervals = SCALES.get(scale_name, SCALES["C Pentatonic Major (Bright)"])

            # Generate our spatial mapping scale
            extended_scale = get_extended_scale(intervals, octaves=octaves, base_midi=base_midi)

            if self.export_checkbox.value:
                session.start_transcribing()
                self.cft(self.log_view.write, "[bold green]Transcription started...[/bold green]")

            self.cft(self.log_view.write, f"[bold green]Playing {scale_name}...[/bold green]")

            for event in self.flow.events:
                if self._stop_event.is_set():
                    break

                try:
                    # Extract the first space from the multi-way branches for deterministic music
                    space = next(event.spaces)
                    cells = list(space.get_all_cells())
                except StopIteration:
                    continue

                elements_to_play = []

                # Map the cells to pitch scale degrees and instruments
                for i, cell in enumerate(cells):
                    val = str(cell.quanta).strip()
                    if val and val not in ignored_chars:

                        # Instrument Resolution
                        instr = instr_map.get(val, base_instrument_name)
                        is_drum = instr.lower().startswith("drumkit") or instr.lower() in ("percussion", "drums")

                        # Pitch / Note Resolution
                        if mapping_mode == "position":
                            scale_index = i
                        elif mapping_mode == "quanta":
                            scale_index = sum(ord(c) for c in val)
                        else:
                            scale_index = sum(ord(c) for c in val) + i

                        # Drums require specific MIDI notes (General MIDI Drums: 35-81).
                        # High melodic pitches (e.g., > 81) produce no sound on drum tracks!
                        if is_drum:
                            pitch = 35 + (scale_index % 47)
                        else:
                            pitch = extended_scale[scale_index % len(extended_scale)]

                        elements_to_play.append((i, val, pitch, instr))

                if not elements_to_play:
                    self.cft(self.log_view.write, f"Event {event.time}: [grey]Rest[/grey]")
                    if not self._wait_interruptable(session, 1.0): break
                    continue

                if playback_timing == "chord":
                    # Play all notes for this event simultaneously across multiple instruments
                    log_str = ", ".join(f"{v}->{p}({i_name})" for _, v, p, i_name in elements_to_play)
                    self.cft(self.log_view.write, f"Event {event.time}: [blue]Chord [{log_str}][/blue]")

                    for _, _, pitch, instr in elements_to_play:
                        part = get_part(instr)
                        part.play_note(pitch, 0.6, 1.0, blocking=False)

                    if not self._wait_interruptable(session, 1.0): break
                else:
                    # Play notes sequentially (Arpeggio style). Each note gets 0.25 beats (16th note)
                    log_str = ", ".join(f"[{idx}]{v}->{p}({i_name})" for idx, v, p, i_name in elements_to_play)
                    self.cft(self.log_view.write, f"Event {event.time}: [blue]Seq [{log_str}][/blue]")

                    note_dur = 0.25
                    for idx, val, pitch, instr in elements_to_play:
                        if self._stop_event.is_set(): break
                        part = get_part(instr)
                        part.play_note(pitch, 0.6, note_dur, blocking=False)
                        if not self._wait_interruptable(session, note_dur): break

            # ==== Cleanup and Export Pipeline ====
            if self.export_checkbox.value and not self._stop_event.is_set():
                self.cft(self.log_view.write, "\n[bold cyan]Processing Performance Export...[/bold cyan]")
                performance = session.stop_transcribing()

                export_fmt = self.export_format.value
                export_path = self.model.project_path / f"cellular_score_{self.model.file_path.stem}.{export_fmt}"

                try:
                    if export_fmt == 'xml':
                        # Valid SCAMP 0.8+ API sequence to export MusicXML
                        score = performance.to_score(title=f"Cellular Automata - {scale_name}")
                        score.export_music_xml(str(export_path))
                        self.cft(self.log_view.write, f"[bold green]Exported MusicXML to: {export_path}[/bold green]")
                    elif export_fmt == 'mid':
                        performance.export_to_midi_file(str(export_path))
                        self.cft(self.log_view.write, f"[bold green]Exported MIDI to: {export_path}[/bold green]")

                except Exception as e:
                    self.cft(self.log_view.write, f"[bold red]Failed to export: {str(e)}[/bold red]")

        except Exception as e:
            self.cft(self.log_view.write, f"[bold red]Playback Error: {str(e)}[/bold red]")

        finally:
            # Prevents sustained instruments (Cello, etc.) from ringing out indefinitely.
            if session is not None:
                try:
                    session.kill()
                except Exception:
                    pass

            self.cft(self.log_view.write, "\n[bold yellow]Playback concluded.[/bold yellow]")
            self._is_playing = False
