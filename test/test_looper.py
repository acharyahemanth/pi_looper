import time
from pilooper.record import Mic
from pilooper.playback import Speaker
from pilooper.mixer import Mixer
import numpy as np

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


@app.command()
def test_mixer():
    mixer = Mixer.create_mixer(track_length_seconds=10)

    num_record_samples = 44_100 * 1
    mic_audio_1 = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples,
    )
    mic_audio_2 = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples,
    )

    mixer.mic_callback(mic_audio_1.tobytes(), num_record_samples, 0, {})
    mixer.mix()

    speaker_audio_1 = np.frombuffer(mixer.speaker_track.track.data, dtype=np.int16)
    speaker_audio_1 = speaker_audio_1[:num_record_samples]
    assert mixer.speaker_track.track.length == num_record_samples * 2
    assert mixer.speaker_track.track.rw_idx == 0
    assert np.allclose(mic_audio_1, speaker_audio_1)
    print("mix-1 success!")

    mixer.mic_callback(mic_audio_2.tobytes(), num_record_samples, 0, {})
    mixer.mix()

    speaker_audio_2 = np.frombuffer(mixer.speaker_track.track.data, dtype=np.int16)
    speaker_audio_2 = speaker_audio_2[:num_record_samples]
    assert mixer.speaker_track.track.length == num_record_samples * 2
    assert mixer.speaker_track.track.rw_idx == 0
    expected_mix = mic_audio_1.astype(np.float32) + mic_audio_2.astype(np.float32)
    expected_mix = np.clip(
        expected_mix, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
    )
    assert np.allclose(speaker_audio_2.astype(np.float32), expected_mix)
    print("mix-2 success!")

    print("TEST PASS!")


if __name__ == "__main__":
    app()
