from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Log
from pilooper.mixer import Mixer
from pilooper.record import Mic
from pilooper.playback import Speaker


class Looper(App):
    """a terminal based looping app"""

    BINDINGS = [
        ("r", "start_record", "Record new track"),
        ("s", "stop_record", "Stop recording and mix new track"),
    ]

    def __init__(self):
        super().__init__()
        self.dark = True
        max_track_length_seconds = 10
        self.mixer = Mixer.create_mixer(track_length_seconds=max_track_length_seconds)
        self.mic = Mic.from_blueyeti(callback=self.mixer.mic_callback)
        self.speaker = Speaker.from_bt_headphones(callback=self.mixer.speaker_callback)
        self.speaker.start()

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        yield Log()
        yield Footer()

    def action_start_record(self) -> None:
        log = self.query_one(Log)
        log.write_line("start recording new track...")
        self.mic.start()

    def action_stop_record(self) -> None:
        log = self.query_one(Log)
        log.write_line("stop recording new track and mix...")
        self.mic.stop()
        self.mixer.mix()


if __name__ == "__main__":
    app = Looper()
    app.run()
