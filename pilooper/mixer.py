from __future__ import annotations
from pathlib import Path
import numpy as np
from dataclasses import dataclass
import pyaudio
import pilooper.constants as constants
from threading import Lock
import logging
from pilooper.track import SpeakerTrack, MicTrack, Track
from pilooper.metronome import Metronome

Pa_Callback_Flags = (
    pyaudio.paInputUnderflow
    | pyaudio.paInputOverflow
    | pyaudio.paOutputOverflow
    | pyaudio.paOutputUnderflowed
)


@dataclass
class Mixer:
    mic_track: MicTrack
    speaker_track: SpeakerTrack
    mixed_track: Track
    track_length_seconds: int
    logger: logging.Logger
    metronome: Metronome | None
    bpm: int | None
    clip_50: bool | None  # mic tracks are clipped to 50% to avoid pedal clicks
    save_on_mix: bool = False

    @classmethod
    def create_mixer(cls, track_length_seconds: int, log_level=logging.INFO):
        buff_len = constants.SAMPLING_RATE * track_length_seconds * 2  # int16
        logger = logging.getLogger("mixer")
        logger.setLevel(log_level)
        return cls(
            mic_track=MicTrack(track=Track(data=bytearray(buff_len), mutex=Lock())),
            speaker_track=SpeakerTrack(
                track=Track(data=bytearray(buff_len), mutex=Lock())
            ),
            mixed_track=Track(data=bytearray(buff_len), mutex=Lock()),
            track_length_seconds=track_length_seconds,
            logger=logger,
            metronome=None,
            bpm=None,
            clip_50=False,
            save_on_mix=False,
        )

    def __post_init__(self):
        import shutil

        if self.save_on_mix:
            out = Path("./saved_tracks")
            if out.exists():
                shutil.rmtree(Path("./saved_tracks"))

    def reset_mic_track(self):
        with self.mic_track.track.mutex:
            self.mic_track.reset()

    def mic_callback(
        self, in_data: bytes, frame_count: int, _: dict, __: Pa_Callback_Flags
    ):
        self.mic_track.save(in_data, frame_count)
        return None, pyaudio.paContinue

    def speaker_callback(
        self, _: None, frame_count: int, __: dict, ___: Pa_Callback_Flags
    ):
        out_data = self.speaker_track.next(frame_count=frame_count)
        return out_data, pyaudio.paContinue

    def add_metronome(self, bpm: int):
        with self.speaker_track.track.mutex:
            wav_file = Path("/home/acharyahemanth/dev/drumstick_16.wav")
            self.metronome = Metronome.from_file(
                bpm=bpm,
                wav_file=wav_file,
                track_length_seconds=self.track_length_seconds,
            )
            self._update_speaker()

    def start_metronome(self):
        if self.metronome is None:
            return

        with self.metronome.track.mutex:
            self.metronome.enabled = True

        self._update_speaker()

    def stop_metronome(self):
        if self.metronome is None:
            return

        with self.metronome.track.mutex:
            self.metronome.enabled = False

        self._update_speaker()

    def _update_speaker(self):
        def _no_metronome():
            self.speaker_track.track.data = self.mixed_track.data
            self.speaker_track.track.length_bytes = self.mixed_track.length_bytes

        self.speaker_track.reset_playback()
        match self.metronome:
            case None:
                _no_metronome()
            case Metronome():
                with self.metronome.track.mutex:
                    if not self.metronome.enabled:
                        _no_metronome()
                        return
                    if self.mixed_track.length_bytes == 0:
                        # nothing mixed yet, just copy over the metronome
                        self.speaker_track.track.data = self.metronome.track.data
                        self.speaker_track.track.length_bytes = (
                            self.metronome.track.length_bytes
                        )
                    else:
                        # mix metronome with mixed_track
                        np_mixed = np.frombuffer(self.mixed_track.data, dtype=np.int16)
                        np_metronome = np.frombuffer(
                            self.metronome.track.data, dtype=np.int16
                        )
                        new_mixed = np_mixed.astype(np.int32) + np_metronome.astype(
                            np.int32
                        )
                        new_mixed = np.clip(
                            new_mixed,
                            a_min=np.iinfo(np.int16).min,
                            a_max=np.iinfo(np.int16).max,
                        )
                        new_mixed = new_mixed.astype(np.int16)
                        self.speaker_track.track.data = bytearray(new_mixed.tobytes())
                        self.speaker_track.track.data[
                            self.mixed_track.length_bytes :
                        ] = bytearray(
                            len(self.speaker_track.track.data)
                            - self.mixed_track.length_bytes
                        )
                        self.speaker_track.track.length_bytes = (
                            self.mixed_track.length_bytes
                        )
            case _:
                assert False

    def save_mix_track(self):
        import wave

        out = Path("./saved_tracks")
        out.mkdir(exist_ok=True, parents=True)

        idx = len(list(out.glob("**/*.wav")))
        fname = f"track_{idx}.wav"

        with wave.open(str(out / fname), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(constants.SAMPLING_RATE)
            wf.writeframes(self.mixed_track.data[: self.mixed_track.length_bytes])

    def set_bpm(self, bpm: int | None):
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.bpm = bpm

    def set_clip50(self, clip: bool | None):
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.clip_50 = clip

    def mix(self):
        # TODO: this pattern of external mutex access seems quite risky in terms
        # of creating dead-locks
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            if self.mic_track.track.length_bytes == 0:
                return
            self.logger.debug("mix()")

            # use bpm to correct for recording delays
            if self.bpm is not None:
                self.mic_track.clip_to_beat_boundary(self.bpm)

            # clip to first half of the track to avoid pedal click
            if self.clip_50:
                self.mic_track.clip_50()

            # no speaker track so far, just copy over the mic track
            if self.mixed_track.length_bytes == 0:
                num_bytes = self.mic_track.track.length_bytes
                self.mixed_track.data[:num_bytes] = self.mic_track.track.data[
                    :num_bytes
                ]
                self.mixed_track.length_bytes = num_bytes
                self.mic_track.reset()
                self._update_speaker()
                if self.save_on_mix:
                    self.save_mix_track()
                self.logger.debug(
                    f"init speaker track by copying over mic track, mixed_track_len : {self.mixed_track.length_bytes}"
                )
                return

            print("mixing mic track with speaker track")
            print(
                f"prev mixed track len : {self.mixed_track.length_bytes}, mic track len : {self.mic_track.track.length_bytes}"
            )

            # create np buffers (no copies at this point)
            np_mixed = np.frombuffer(self.mixed_track.data, dtype=np.int16)
            np_mic = np.frombuffer(self.mic_track.track.data, np.int16)
            assert (
                len(np_mixed) == len(np_mic)
            ), f"mixed and mic tracs arent of same length : {np_mixed.nbytes} / {np_mic.nbytes}"

            # extend smaller track to the size of the larger one
            def _extend(x: np.ndarray, x_length_bytes: int, by_bytes: int):
                x_length = x_length_bytes // 2
                by = by_bytes // 2
                extend_to = min(x_length + by, len(x))
                num_tile = extend_to // x_length
                extended = np.zeros_like(x)
                extended[: num_tile * x_length] = np.tile(x[:x_length], num_tile)
                num_pad = extend_to - num_tile * x_length
                if num_pad > 0:
                    pad_start = num_tile * x_length
                    extended[pad_start : pad_start + num_pad] = x[:num_pad]

                print(f"_extend() : extend_to : {extend_to}, num_tile : {num_tile}")
                return extended, extend_to * 2

            extend_mixed_track = (
                self.mixed_track.length_bytes < self.mic_track.track.length_bytes
            )
            extend_by_bytes = abs(
                self.mixed_track.length_bytes - self.mic_track.track.length_bytes
            )
            print(
                f"extend_mixed_track : {extend_mixed_track} extend_mic_track : {not extend_mixed_track} extend_by : {extend_by_bytes}"
            )
            new_mixed_len_bytes = self.mixed_track.length_bytes
            if extend_mixed_track:
                np_mixed, new_mixed_len_bytes = _extend(
                    np_mixed, self.mixed_track.length_bytes, extend_by_bytes
                )
            else:
                np_mic, _ = _extend(
                    np_mic, self.mic_track.track.length_bytes, extend_by_bytes
                )

            assert (
                len(np_mixed) == len(np_mic)
            ), f"mixed and mic tracs arent of same length_bytes : {np_mixed.nbytes} / {np_mic.nbytes}"

            # mix new track
            new_mixed = np_mixed.astype(np.int32) + np_mic.astype(np.int32)
            new_mixed = np.clip(
                new_mixed, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
            )
            new_mixed = new_mixed.astype(np.int16)

            # store mixed track
            self.mixed_track.data = bytearray(new_mixed.tobytes())
            self.mixed_track.length_bytes = new_mixed_len_bytes

            if self.save_on_mix:
                self.save_mix_track()

            # update speaker track
            self.mic_track.reset()
            self._update_speaker()

    def reset(self):
        """resets both mic and speaker tracks (without releasing their memory)"""
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.mic_track.reset()
            self.speaker_track.reset()
            self.mixed_track.reset()
