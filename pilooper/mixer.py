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

        num_track_bytes = constants.SAMPLING_RATE * track_length_seconds * 2
        num_track_bytes += num_track_bytes % len(wav_audio)
        np_wav_audio = np.frombuffer(wav_audio, dtype=np.int16)
        assert (
            num_track_bytes % len(wav_audio) == 0
        ), f"somethings off with the clipping / padding calculations : {num_track_bytes} / {len(wav_audio)}"
        num_tile = num_track_bytes // len(wav_audio)
        np_track = np.tile(np_wav_audio, num_tile)

        return cls(
            bpm=bpm,
            track=Track(
                data=bytearray(np_track.tobytes()),
                mutex=Lock(),
                length_bytes=num_track_bytes,
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


@dataclass
class Mixer:
    mic_track: MicTrack
    speaker_track: SpeakerTrack
    logger: logging.Logger

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
            logger=logger,
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

    def mix(self):
        # TODO: this pattern of external mutex access seems quite risky in terms
        # of creating dead-locks
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            if self.mic_track.track.length_bytes == 0:
                return
            self.logger.debug("mix()")

            # no speaker track so far, just copy over the mic track
            if self.speaker_track.track.length_bytes == 0:
                num_bytes = self.mic_track.track.length_bytes
                self.speaker_track.track.data[:num_bytes] = self.mic_track.track.data[
                    :num_bytes
                ]
                self.speaker_track.track.length_bytes = num_bytes
                self.mic_track.reset()
                self.speaker_track.reset_playback()
                self.logger.debug(
                    f"init speaker track by copying over mic track, speaker_len : {self.speaker_track.track.length_bytes}"
                )
                return

            self.logger.debug("mixing mic track with speaker track")
            self.logger.debug(
                f"prev speaker track len : {self.speaker_track.track.length_bytes}, mic track len : {self.mic_track.track.length_bytes}"
            )

            # create np buffers (no copies at this point)
            np_speaker = np.frombuffer(self.speaker_track.track.data, dtype=np.int16)
            np_mic = np.frombuffer(self.mic_track.track.data, np.int16)
            assert (
                len(np_speaker) == len(np_mic)
            ), f"speaker and mic tracs arent of same length : {np_speaker.nbytes} / {np_mic.nbytes}"

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

            extend_speaker_track = (
                self.speaker_track.track.length_bytes
                < self.mic_track.track.length_bytes
            )
            extend_by_bytes = abs(
                self.speaker_track.track.length_bytes
                - self.mic_track.track.length_bytes
            )
            self.logger.debug(
                f"extend_speaker_track : {extend_speaker_track} extend_mic_track : {not extend_speaker_track} extend_by : {extend_by_bytes}"
            )
            new_speaker_len_bytes = None
            if extend_speaker_track:
                np_speaker, new_speaker_len_bytes = _extend(
                    np_speaker, self.speaker_track.track.length_bytes, extend_by_bytes
                )
            else:
                np_mic, _ = _extend(
                    np_mic, self.mic_track.track.length_bytes, extend_by_bytes
                )

            assert (
                len(np_speaker) == len(np_mic)
            ), f"speaker and mic tracs arent of same length_bytes : {np_speaker.nbytes} / {np_mic.nbytes}"

            # mix and take care of clipping
            mixed = np_speaker.astype(np.int32) + np_mic.astype(np.int32)
            mixed = np.clip(
                mixed, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
            )
            mixed = mixed.astype(np.int16)

            self.speaker_track.track.data = bytearray(mixed.tobytes())
            if new_speaker_len_bytes:
                self.speaker_track.track.length_bytes = new_speaker_len_bytes
            self.mic_track.reset()
            self.speaker_track.reset_playback()

    def reset(self):
        """resets both mic and speaker tracks (without releasing their memory)"""
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            self.mic_track.reset()
            self.speaker_track.reset()
