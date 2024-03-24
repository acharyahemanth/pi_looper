import time
from pilooper.record import Mic
from pilooper.playback import Speaker
from pilooper.mixer import Mixer

from typer import Typer

app = Typer()


@app.command()
def test_looper():
    record_time_seconds = 3

    mixer = Mixer.create_mixer(track_length_seconds=record_time_seconds)
    mic = Mic.from_blueyeti(mixer=mixer)
    speaker = Speaker.from_bt_headphones(mixer=mixer)

    print("starting speaker...")
    speaker.start()
    print(f"starting mic, record for {record_time_seconds} seconds...")
    mic.start()

    time.sleep(record_time_seconds)

    print("stopping mic")
    mic.stop()

    print("mixing...")
    mixer.mix()

    print("looping for 10 seconds...")
    time.sleep(10)
    print("done!")


if __name__ == "__main__":
    app()
