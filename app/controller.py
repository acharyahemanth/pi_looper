from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import assert_never
import streamlit as st
from typer.models import NoneType

from pilooper.mixer import Mixer
from pilooper.playback import Speaker
from pilooper.record import Mic


@dataclass
class MaybeInt:
    value: int | None
    has_changed: bool = False


@dataclass
class MaybeBool:
    value: bool
    has_changed: bool = False

    def __bool__(self) -> bool:
        return self.has_changed and self.value


@dataclass
class UIState:
    bpm: MaybeInt
    enable_metronome: MaybeBool
    enable_beat_sync: MaybeBool
    record: MaybeBool
    stop: MaybeBool
    reset: MaybeBool
    mix: MaybeBool


class ControllerState(Enum):
    READY_TO_RECORD = 0
    RECORDING = 1


def warn(msg: str):
    st.toast(f"⚠ {msg}")


@dataclass
class Controller:
    mixer: Mixer
    mic: Mic
    speaker: Speaker
    state: ControllerState

    @classmethod
    def from_defaults(cls, track_length_seconds: int) -> Controller:
        mixer = Mixer.create_mixer(track_length_seconds=track_length_seconds)
        mic = Mic.from_blueyeti(callback=mixer.mic_callback)
        speaker = Speaker.from_bt_headphones(callback=mixer.speaker_callback)

        return cls(
            mixer=mixer, mic=mic, speaker=speaker, state=ControllerState.READY_TO_RECORD
        )

    def _start_metronome(self, bpm: MaybeInt):
        assert bpm.value is not None
        self.mixer.add_metronome(bpm.value)
        self.mixer.start_metronome()

    def _state_ready_to_record(self, ui_state: UIState):
        # metronome
        if ui_state.enable_metronome.has_changed:
            if ui_state.enable_metronome.value:
                self._start_metronome(ui_state.bpm)
            else:
                self.mixer.stop_metronome()

        # beat sync
        if ui_state.enable_beat_sync.has_changed:
            if ui_state.enable_beat_sync.value:
                assert ui_state.bpm.value is not None
                bpm = ui_state.bpm.value
            else:
                bpm = None
            self.mixer.set_bpm(bpm)

        # bpm has changed, restart metronome / beat-sync
        if ui_state.bpm.has_changed:
            if self.mixer.metronome is not None:
                self.mixer.stop_metronome()
                self._start_metronome(ui_state.bpm)
            if ui_state.enable_beat_sync.value:
                self.mixer.set_bpm(ui_state.bpm.value)

        assert ui_state.stop.value is False
        assert ui_state.mix.value is False

        # reset everything so far
        if ui_state.reset:
            self.mixer.reset()
            return

        # start recording
        if ui_state.record:
            self.mic.start()
            self.state = ControllerState.RECORDING

    def _state_recording(self, ui_state: UIState):
        assert not ui_state.bpm.has_changed
        assert not ui_state.enable_metronome.has_changed
        assert not ui_state.enable_beat_sync.has_changed

        if ui_state.record:
            warn("mixer is already recording!")
            return

        if ui_state.stop:
            self.mic.stop()
            self.mixer.reset_mic_track()
            self.state = ControllerState.READY_TO_RECORD
            return

        # reset everything so far
        if ui_state.reset:
            self.mic.stop()
            self.mixer.reset()
            self.state = ControllerState.READY_TO_RECORD
            return

        if ui_state.mix:
            self.mic.stop()
            self.mixer.mix()
            self.state = ControllerState.READY_TO_RECORD
            return

        assert False, f"ui_state : {ui_state}"

    def update(self, ui_state: UIState):
        match self.state:
            case ControllerState.READY_TO_RECORD:
                self._state_ready_to_record(ui_state)
            case ControllerState.RECORDING:
                self._state_recording(ui_state)
            case _:
                assert_never(self.state)
