import numpy as np
from dataclasses import dataclass
from collections import deque
import pyaudio
import pilooper.constants as constants
from threading import Lock

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
    length: int = 0


@dataclass
class SpeakerTrack:
    track: Track

    def next(self, frame_count: int) -> bytes:
        if not self.track.mutex.acquire():
            print("speaker_callback() : speaker blocked, returning...")
            return bytes(0)

        # no data yet, play nothing
        if self.track.length == 0:
            self.track.mutex.release()
            return bytes(frame_count * 2)

        if self.track.length < frame_count * 2:
            print(
                f"warning : not enough speaker data, {len(self.track.data)/2}/{frame_count} speaker stream may stop!"
            )

        num_bytes = min(frame_count * 2, self.track.length)
        start = self.track.rw_idx
        end = (self.track.rw_idx + num_bytes) % self.track.length
        if end < start:
            mem = memoryview(
                self.track.data[start : self.track.length] + self.track.data[:end]
            )
        else:
            mem = memoryview(self.track.data[start:end])

        self.track.rw_idx = end
        self.track.mutex.release()
        return bytes(mem)

    def reset_playback(self):
        self.track.rw_idx = 0


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
        self.track.length = end
        self.track.mutex.release()

        return True

    def reset(self):
        self.track.rw_idx = 0
        self.track.length = 0
        self.is_full = False


@dataclass
class Mixer:
    mic_track: MicTrack
    speaker_track: SpeakerTrack

    @classmethod
    def create_mixer(cls, track_length_seconds: int):
        buff_len = constants.SAMPLING_RATE * track_length_seconds * 2  # int16
        return cls(
            mic_track=MicTrack(track=Track(data=bytearray(buff_len), mutex=Lock())),
            speaker_track=SpeakerTrack(
                track=Track(data=bytearray(buff_len), mutex=Lock())
            ),
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
        with self.mic_track.track.mutex, self.speaker_track.track.mutex:
            if self.mic_track.track.length == 0:
                return

            # no speaker track so far, just copy over the mic track
            if self.speaker_track.track.length == 0:
                num_bytes = self.mic_track.track.length
                self.speaker_track.track.data[:num_bytes] = self.mic_track.track.data[
                    :num_bytes
                ]
                self.speaker_track.track.length = num_bytes
                self.mic_track.reset()
                self.speaker_track.reset_playback()
                return

            # create np buffers (no copies at this point)
            np_speaker = np.frombuffer(self.speaker_track.track.data, dtype=np.int16)
            np_mic = np.frombuffer(self.mic_track.track.data, np.int16)
            assert (
                len(np_speaker) == len(np_mic)
            ), f"speaker and mic tracs arent of same length : {len(np_speaker)} / {len(np_mic)}"

            # extend smaller track to the size of the larger one
            def _extend(x: np.ndarray, x_length: int, by: int):
                extend_to = min(x_length + by, x.nbytes)
                num_tile = extend_to // x_length
                extended = np.zeros_like(x)
                extended[: num_tile * x_length] = np.tile(x[:x_length], num_tile)
                return extended, extend_to

            extend_speaker_track = (
                self.speaker_track.track.length < self.mic_track.track.length
            )
            extend_by = abs(
                self.speaker_track.track.length - self.mic_track.track.length
            )
            new_speaker_len = None
            if extend_speaker_track:
                np_speaker, new_speaker_len = _extend(
                    np_speaker, self.speaker_track.track.length, extend_by
                )
            else:
                np_mic, _ = _extend(np_mic, self.mic_track.track.length, extend_by)

            assert (
                len(np_speaker) == len(np_mic)
            ), f"speaker and mic tracs arent of same length : {len(np_speaker)} / {len(np_mic)}"

            # mix and take care of clipping
            mixed = np_speaker.astype(np.int32) + np_mic.astype(np.int32)
            mixed = np.clip(
                mixed, a_min=np.iinfo(np.int16).min, a_max=np.iinfo(np.int16).max
            )
            mixed = mixed.astype(np.int16)

            self.speaker_track.track.data = bytearray(mixed.tobytes())
            if new_speaker_len:
                self.speaker_track.track.length = new_speaker_len
            self.mic_track.reset()
            self.speaker_track.reset_playback()
