from __future__ import annotations
from dataclasses import dataclass
from pilooper.track import SpeakerTrack, Track
import pilooper.constants as constants
import wave
from pathlib import Path
import numpy as np
from threading import Lock


@dataclass
class Metronome(SpeakerTrack):
    bpm: int
    enabled: bool

    @classmethod
    def from_file(
        cls, wav_file: Path, bpm: int, track_length_seconds: int
    ) -> Metronome:
        wav_audio = bytearray(0)
        with wave.open(str(wav_file), "rb") as wf:
            while len(data := wf.readframes(1024)):  # Requires Python 3.8+ for :=
                wav_audio.extend(data)
        # assert (
        #    len(wav_audio) < constants.SAMPLING_RATE
        # ), "this method assumes wav file duration < 1s"
        samples_per_minute = constants.SAMPLING_RATE * 60
        samples_per_beat = (
            samples_per_minute // bpm
        )  # TODO : is this the right thing to do?

        # clip / extend wav audio to samples per beat
        num_wav_samples = len(wav_audio) // 2
        if num_wav_samples < samples_per_beat:
            padding = samples_per_beat - num_wav_samples
            zeros = np.zeros(padding, dtype=np.int16)
            wav_audio.extend(zeros.tobytes())
        else:
            clip_bytes = samples_per_beat * 2
            wav_audio = wav_audio[:clip_bytes]
        assert (
            len(wav_audio) / 2 == samples_per_beat
        ), f"havent clipped / padded correctly : {len(wav_audio) / 2}, {samples_per_beat}"
        np_wav_audio = np.frombuffer(wav_audio, dtype=np.int16)

        np_track = np.zeros(
            constants.SAMPLING_RATE * track_length_seconds, dtype=np.int16
        )
        num_track_filled = len(np_track) - len(np_track) % samples_per_beat
        num_tile = num_track_filled // samples_per_beat
        np_track[:num_track_filled] = np.tile(np_wav_audio, num_tile)

        return cls(
            bpm=bpm,
            enabled=True,
            track=Track(
                data=bytearray(np_track.tobytes()),
                mutex=Lock(),
                length_bytes=num_track_filled * 2,
            ),
        )
