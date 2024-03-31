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

    def record():
        mic.start()
        time.sleep(record_time_seconds)
        mic.stop()

    print("starting speaker...")
    speaker.start()

    for _ in range(2):
        print("next record begins in 3 seconds...")
        time.sleep(3)
        print(f"start record for {record_time_seconds} seconds...")
        record()
        print("mixing...")
        mixer.mix()

    print("done looping, playing back mixed audio...")
    time.sleep(2 * record_time_seconds)

    print("done!")


if __name__ == "__main__":
    app()
