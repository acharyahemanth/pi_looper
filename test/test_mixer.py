import logging
from pilooper.record import Mic
from pilooper.playback import Speaker
from pilooper.mixer import Mixer
from typer import Typer
import numpy as np

app = Typer()


@app.command()
def test_basic():
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
    assert mixer.speaker_track.track.length_bytes == num_record_samples * 2
    assert mixer.speaker_track.track.rw_idx == 0
    assert np.allclose(mic_audio_1, speaker_audio_1)
    print("mix-1 success!")

    mixer.mic_callback(mic_audio_2.tobytes(), num_record_samples, 0, {})
    mixer.mix()

    speaker_audio_2 = np.frombuffer(mixer.speaker_track.track.data, dtype=np.int16)
    speaker_audio_2 = speaker_audio_2[:num_record_samples]
    assert mixer.speaker_track.track.length_bytes == num_record_samples * 2
    assert mixer.speaker_track.track.rw_idx == 0
    expected_mix = mic_audio_1.astype(np.float32) + mic_audio_2.astype(np.float32)
    expected_mix = np.clip(
        expected_mix, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
    )
    assert np.allclose(speaker_audio_2.astype(np.float32), expected_mix)
    print("mix-2 success!")

    print("TEST PASS!")


@app.command()
def test_track_lengths():
    mixer = Mixer.create_mixer(track_length_seconds=10, log_level=logging.DEBUG)

    num_record_samples_long = 44_100 * 2
    num_record_samples_short = 44_100 * 1
    mic_audio_long = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples_long,
    )
    mic_audio_short = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples_short,
    )

    # check if speaker track is extended correctly
    def check_mix():
        assert (
            mixer.speaker_track.track.length_bytes == 2 * num_record_samples_long
        ), "speaker track is not off correct length"
        np_speaker = np.frombuffer(mixer.speaker_track.track.data, dtype=np.int16)[
            :num_record_samples_long
        ]
        np_mic_short_ext = np.concatenate([mic_audio_short, mic_audio_short], axis=0)

        expected_mix = mic_audio_long.astype(np.float32) + np_mic_short_ext.astype(
            np.float32
        )
        expected_mix = np.clip(
            expected_mix, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
        )

        assert np.allclose(np_speaker.astype(np.float32), expected_mix)

    # record longer track
    mixer.mic_callback(mic_audio_long.tobytes(), num_record_samples_long, 0, {})
    mixer.mix()

    # record shorter track
    mixer.mic_callback(mic_audio_short.tobytes(), num_record_samples_short, 0, {})
    mixer.mix()

    check_mix()

    # add mic tracks the other way round
    mixer.reset()

    # record shorter track
    mixer.mic_callback(mic_audio_short.tobytes(), num_record_samples_short, 0, {})
    mixer.mix()

    # record longer track
    mixer.mic_callback(mic_audio_long.tobytes(), num_record_samples_long, 0, {})
    mixer.mix()

    check_mix()

    print("TEST PASS!")


@app.command()
def test_overflow():
    mixer = Mixer.create_mixer(track_length_seconds=1, log_level=logging.DEBUG)

    num_record_samples_first = 44_100 * 1
    num_record_samples_second = 44_100 * 1
    mic_audio_first = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples_first,
    )
    mic_audio_second = np.random.randint(
        low=np.iinfo(np.int16).min,
        high=np.iinfo(np.int16).max,
        dtype=np.int16,
        size=num_record_samples_second,
    )

    # check if speaker track is extended correctly
    def check_mix():
        assert (
            mixer.speaker_track.track.length_bytes == 2 * num_record_samples_first
        ), "speaker track is not off correct length"
        np_speaker = np.frombuffer(mixer.speaker_track.track.data, dtype=np.int16)[
            :num_record_samples_first
        ]
        assert np.allclose(np_speaker, mic_audio_first)

    # record first track
    mixer.mic_callback(mic_audio_first.tobytes(), num_record_samples_first, 0, {})

    # record second track
    mixer.mic_callback(mic_audio_second.tobytes(), num_record_samples_second, 0, {})

    mixer.mix()

    check_mix()


if __name__ == "__main__":
    app()
