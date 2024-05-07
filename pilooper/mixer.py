from __future__ import annotations
from pathlib import Path
import wave
import numpy as np
from dataclasses import dataclass
from collections import deque
import pyaudio
import pilooper.constants as constants
from threading import Lock
import logging

Pa_Callback_Flags = (
    pyaudio.paInputUnderflow
    | pyaudio.paInputOverflow
    | pyaudio.paOutputOverflow
    | pyaudio.paOutputUnderflowed
)


@dataclass
class Track:
    data: bytearray
    mutex: Lock
    # index to start reading / writing (depending on speaker / mic)
    rw_idx: int = 0
    # length of data thats filled (in bytes)
    length_bytes: int = 0

    def reset(self):
        self.rw_idx = 0
        self.length_bytes = 0


@dataclass
class SpeakerTrack:
    track: Track

    def next(self, frame_count: int) -> bytes:
        if not self.track.mutex.acquire():
            print("speaker_callback() : speaker blocked, returning...")
            return bytes(0)

        # no data yet, play nothing
        if self.track.length_bytes == 0:
            self.track.mutex.release()
            return bytes(frame_count * 2)

        if self.track.length_bytes < frame_count * 2:
            print(
                f"warning : not enough speaker data, {len(self.track.data)/2}/{frame_count} speaker stream may stop!"
            )

        num_bytes = min(frame_count * 2, self.track.length_bytes)
        start = self.track.rw_idx
        end = (self.track.rw_idx + num_bytes) % (self.track.length_bytes + 1)
        if end < start:
            end += 1
            mem = memoryview(
                self.track.data[start : self.track.length_bytes] + self.track.data[:end]
            )
        else:
            mem = memoryview(self.track.data[start:end])
        assert (
            len(mem) == num_bytes
        ), f"didnt pick correct number of bytes : start : {start}, end : {end}, track_length : {self.track.length_bytes}, len(mem) : {len(mem)}"

        self.track.rw_idx = end % self.track.length_bytes
        self.track.mutex.release()
        return bytes(mem)

    def reset_playback(self):
        self.track.rw_idx = 0

    def reset(self):
        self.track.reset()


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


@dataclass
class MicTrack:
    track: Track
    is_full: bool = False

    def save(self, in_data: bytes, frame_count: int) -> bool:
        if self.is_full:
            return False
        if not self.track.mutex.acquire():
            print("mic_callback() : mic blocked, returning...")
            return False

        num_bytes = frame_count * 2
        assert (
            len(in_data) == num_bytes
        ), f"not using int16? len(in_data): {len(in_data)}, frame_count: {frame_count}"

        start = self.track.rw_idx
        end = start + num_bytes
        self.is_full = end >= len(self.track.data)
        if self.is_full:
            end = len(self.track.data)

        num_bytes = end - start
        self.track.data[start:end] = in_data[:num_bytes]
        self.track.rw_idx = end
        self.track.length_bytes = end
        self.track.mutex.release()

        return True

    def reset(self):
        self.track.reset()
        self.is_full = False

    def clip_to_beat_boundary(self, bpm: int):
        samples_per_minute = constants.SAMPLING_RATE * 60
        samples_per_beat = samples_per_minute // bpm
        bytes_per_beat = samples_per_beat * 2
        self.track.length_bytes = (
            self.track.length_bytes // bytes_per_beat
        ) * bytes_per_beat


@dataclass
class Mixer:
    mic_track: MicTrack
    speaker_track: SpeakerTrack
    mixed_track: Track
    track_length_seconds: int
    logger: logging.Logger
    metronome: Metronome | None
    bpm: int | None

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
        )

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

    def set_bpm(self, bpm: int):
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.bpm = bpm

        # TODO: should this method also be smart enough to reset the metronome?

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

            # no speaker track so far, just copy over the mic track
            if self.mixed_track.length_bytes == 0:
                num_bytes = self.mic_track.track.length_bytes
                self.mixed_track.data[:num_bytes] = self.mic_track.track.data[
                    :num_bytes
                ]
                self.mixed_track.length_bytes = num_bytes
                self.mic_track.reset()
                self._update_speaker()
                self.logger.debug(
                    f"init speaker track by copying over mic track, mixed_track_len : {self.mixed_track.length_bytes}"
                )
                return

            self.logger.debug("mixing mic track with speaker track")
            self.logger.debug(
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
                self.logger.debug(
                    f"_extend() : extend_to : {extend_to}, num_tile : {num_tile}"
                )
                return extended, extend_to * 2

            extend_mixed_track = (
                self.mixed_track.length_bytes < self.mic_track.track.length_bytes
            )
            extend_by_bytes = abs(
                self.mixed_track.length_bytes - self.mic_track.track.length_bytes
            )
            self.logger.debug(
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

            # update speaker track
            self.mic_track.reset()
            self._update_speaker()

    def reset(self):
        """resets both mic and speaker tracks (without releasing their memory)"""
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.mic_track.reset()
            self.speaker_track.reset()
            self.mixed_track.reset()
