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
    start_idx: int = 0


@dataclass
class SpeakerTrack:
    track: Track

    def next(self, frame_count: int) -> bytes:
        if not self.track.mutex.acquire():
            print("speaker_callback() : speaker blocked, returning...")
            return bytes(0)

        if len(self.track.data) < frame_count * 2:
            print(
                f"warning : not enough speaker data, {len(self.track.data)/2}/{frame_count} speaker stream may stop!"
            )

        num_bytes = min(frame_count * 2, len(self.track.data))
        start = self.track.start_idx
        end = (self.track.start_idx + num_bytes) % len(self.track.data)
        if end < start:
            mem = memoryview(self.track.data[start:] + self.track.data[:end])
        else:
            mem = memoryview(self.track.data[start:end])

        self.track.start_idx = end
        self.track.mutex.release()
        return bytes(mem)

    def reset_playback(self):
        self.track.start_idx = 0


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

        start = self.track.start_idx
        end = start + num_bytes
        self.is_full = end >= len(self.track.data)
        if self.is_full:
            end = len(self.track.data)

        self.track.data[start:end] = in_data
        self.track.start_idx = end
        self.track.mutex.release()

        return True


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
        self.mic_track.track.mutex.acquire()
        self.speaker_track.track.mutex.acquire()

        """
        TODO: 
        - handle overflows
        - handle mismatched track lengths
        """
        # self.speaker_track.track.data = bytearray(
        #     (
        #         np.frombuffer(self.speaker_track.track.data)
        #         + np.frombuffer(self.mic_track.track.data)
        #     ).tobytes()
        # )
        self.speaker_track.track.data = self.mic_track.track.data
        self.speaker_track.reset_playback()

        self.mic_track.track.mutex.release()
        self.speaker_track.track.mutex.release()
