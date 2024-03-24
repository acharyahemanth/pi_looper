import wave
from dataclasses import dataclass
from pathlib import Path

import pyaudio
import rich
from tqdm import tqdm
from typer import Typer

app = Typer()


@dataclass
class Wire:
    sample_rate: int
    channels: int
    stream: pyaudio.Stream
    sample_format: int

    @classmethod
    def from_defaults(cls):
        pyaud = pyaudio.PyAudio()

        channels = 1
        # sample_rate = int(def_device_info['defaultSampleRate']) # pyright: ignore
        sample_rate = 44_100  # reducing the sampling rate because of input overflows!
        sample_format = pyaudio.paInt16
        stream = pyaud.open(
            rate=sample_rate,
            channels=channels,
            format=sample_format,
            input=True,
            output=True,
            start=False,
        )

        return cls(
            channels=channels,
            sample_rate=sample_rate,
            sample_format=sample_format,
            stream=stream,
        )  # pyright: ignore

    def go(self, record_seconds: int):
        self.stream.start_stream()
        print("* recording")
        chunk = 100
        for _ in range(0, int(self.sample_rate / chunk * record_seconds)):
            self.stream.write(
                self.stream.read(chunk, exception_on_overflow=False),
                exception_on_underflow=False,
            )

        self.stream.stop_stream()
        self.stream.close()
        print("* done")


@app.command()
def test(record_seconds: int = 5):
    wire = Wire.from_defaults()
    wire.go(record_seconds)


if __name__ == "__main__":
    app()
