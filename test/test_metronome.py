import time
from pilooper.mixer import Metronome

from pathlib import Path
from typer import Typer
import pyaudio

from pilooper.playback import Speaker


app = Typer()

Pa_Callback_Flags = (
    pyaudio.paInputUnderflow
    | pyaudio.paInputOverflow
    | pyaudio.paOutputOverflow
    | pyaudio.paOutputUnderflowed
)


@app.command()
def live_test_metronome():
    wav_file = Path("/home/acharyahemanth/dev/drumstick_16.wav")
    metronome = Metronome.from_file(bpm=100, wav_file=wav_file, track_length_seconds=3)

    def speaker_callback(_: None, frame_count: int, __: dict, ___: Pa_Callback_Flags):
        out_data = metronome.next(frame_count=frame_count)
        return out_data, pyaudio.paContinue

    speaker = Speaker.from_bt_headphones(callback=speaker_callback)
    print("playing metronome...")
    speaker.start()
    time.sleep(3)
    speaker.stop()


if __name__ == "__main__":
    app()
