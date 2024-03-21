from dataclasses import dataclass
import pyaudio
from pathlib import Path
import wave
from tqdm import tqdm


@dataclass
class Mic:
    name: str
    index: int
    sample_rate: int
    channels: int
    stream: pyaudio.Stream
    sample_format: int

    @classmethod
    def from_blueyeti(cls):
        """
        this is what i see with the usb mic connected,
        was hoping to see a blue-yeti reflected in the name to pick
        this mic out when theres multiple input devices
        default device info
        {
            'index': 6,
            'structVersion': 2,
            'name': 'default',
            'hostApi': 0,
            'maxInputChannels': 128,
            'maxOutputChannels': 128,
            'defaultLowInputLatency': 0.021333333333333333,
            'defaultLowOutputLatency': 0.021333333333333333,
            'defaultHighInputLatency': 0.021333333333333333,
            'defaultHighOutputLatency': 0.021333333333333333,
            'defaultSampleRate': 48000.0
        }
        """
        pyaud = pyaudio.PyAudio()
        def_device_info = pyaud.get_default_input_device_info()

        channels = 1
        # sample_rate = int(def_device_info['defaultSampleRate']) # pyright: ignore
        sample_rate = 44_100  # reducing the sampling rate because of input overflows!
        sample_format = pyaudio.paInt16
        stream = pyaud.open(
            rate=sample_rate,
            channels=channels,
            format=sample_format,
            input=True,
            start=False,
        )

        return cls(
            name=def_device_info["name"],
            index=def_device_info["index"],
            channels=channels,
            sample_rate=sample_rate,
            sample_format=sample_format,
            stream=stream,
        )  # pyright: ignore

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


if __name__ == "__main__":
    mic = Mic.from_blueyeti()
    mic.record_to_file(5, Path("./test.wav"))
