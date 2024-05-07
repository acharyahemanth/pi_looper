from dataclasses import dataclass
from threading import Lock
import pilooper.constants as constants


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
