from typing import assert_never
import wave
from dataclasses import dataclass
from pathlib import Path

import pyaudio
import rich
from typer import Typer

from pilooper.constants import SAMPLING_RATE
from pilooper.mixer import Mixer

app = Typer()


@dataclass
class Speaker:
    name: str
    index: int
    sample_rate: int
    channels: int
    stream: pyaudio.Stream
    sample_format: int

    @classmethod
    def from_bt_headphones(cls, mixer: Mixer | None = None):
        pyaud = pyaudio.PyAudio()
        def_device_info = pyaud.get_default_output_device_info()
        print("using default audio device : ")
        rich.print(def_device_info)

        channels = 1
        sample_rate = SAMPLING_RATE
        sample_format = pyaudio.paInt16
        match mixer:
            case None:
                callback = None
            case Mixer():
                callback = mixer.speaker_callback
            case _:
                assert_never(mixer)
        stream = pyaud.open(
            rate=sample_rate,
            channels=channels,
            format=sample_format,
            output=True,
            start=False,
            stream_callback=callback,  # pyright: ignore
        )

        return cls(
            name=def_device_info["name"],  # pyright: ignore
            index=def_device_info["index"],  # pyright: ignore
            channels=channels,
            sample_rate=sample_rate,
            sample_format=sample_format,
            stream=stream,
        )  # pyright: ignore

    def start(self):
        self.stream.start_stream()

    def stop(self):
        self.stream.stop_stream()

    def __del__(self):
        self.stream.close()

    def play_from_file(self, path: Path):
        self.stream.start_stream()

        with wave.open(str(path), "rb") as wf:
            p = pyaudio.PyAudio()
            chunk = 1024
            while len(data := wf.readframes(chunk)):  # Requires Python 3.8+ for :=
                self.stream.write(data, exception_on_underflow=False)

            self.stream.stop_stream()
            self.stream.close()
            p.terminate()


@app.command()
def test_speaker(wav_file: Path):
    speaker = Speaker.from_bt_headphones()
    speaker.play_from_file(wav_file)


if __name__ == "__main__":
    app()
