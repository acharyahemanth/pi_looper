import wave
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

import pyaudio
import rich
from tqdm import tqdm
from typer import Typer
import time

from pilooper.constants import SAMPLING_RATE
from pilooper.mixer import Mixer

app = Typer()


@dataclass
class Mic:
    name: str
    index: int
    sample_rate: int
    channels: int
    stream: pyaudio.Stream
    sample_format: int

    @classmethod
    def from_blueyeti(cls, mixer: Mixer | None = None):
        pyaud = pyaudio.PyAudio()
        def_device_info = pyaud.get_default_input_device_info()
        print("using default audio device : ")
        rich.print(def_device_info)

        channels = 1
        sample_rate = SAMPLING_RATE
        sample_format = pyaudio.paInt16
        match mixer:
            case None:
                callback = None
            case Mixer():
                callback = mixer.mic_callback
            case _:
                assert_never(mixer)

        pyaud = pyaudio.PyAudio()
        stream = pyaud.open(
            rate=sample_rate,
            channels=channels,
            format=sample_format,
            input=True,
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
        )

    def start(self):
        self.stream.start_stream()

    def stop(self):
        self.stream.stop_stream()

    def __del__(self):
        self.stream.close()

    def record_to_file(self, seconds: float, path: Path):
        self.stream.start_stream()

        with wave.open(str(path), "wb") as wf:
            p = pyaudio.PyAudio()
            wf.setnchannels(self.channels)
            wf.setsampwidth(p.get_sample_size(self.sample_format))
            wf.setframerate(self.sample_rate)

            print("Recording...")
            chunk = 1024
            for _ in tqdm(range(0, (self.sample_rate * seconds) // chunk)):
                wf.writeframes(self.stream.read(chunk, exception_on_overflow=False))
            print("Done!")

            self.stream.stop_stream()
            self.stream.close()
            p.terminate()


@app.command()
def test_mic(record_seconds: int = 5):
    # mic = Mic.from_blueyeti()
    # mic.record_to_file(record_seconds, Path("./test.wav"))

    mixer = Mixer.create_mixer(record_seconds)
    mic = Mic.from_blueyeti(mixer=mixer)
    print("* recording...")
    mic.start()
    time.sleep(record_seconds)
    mic.stop()
    print("done recording!")

    print("writing recorded data to wav file..")
    with wave.open("./test.wav", "wb") as wf:
        wf.setnchannels(mic.channels)
        wf.setsampwidth(2)
        wf.setframerate(mic.sample_rate)

        chunk = 1024
        data = mixer.mic_track.track.data
        for i in tqdm(range(0, len(data) // chunk)):
            start = i * chunk
            end = start + chunk
            wf.writeframes(data[start:end])
    print("done")


if __name__ == "__main__":
    app()
