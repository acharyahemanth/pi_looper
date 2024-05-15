from ast import Call
from typing import Callable, dataclass_transform
import streamlit as st
from streamlit.type_util import maybe_tuple_to_list
from streamlit_extras.stylable_container import stylable_container
from dataclasses import dataclass, asdict, field

from app.controller import Controller, MaybeBool, MaybeInt, UIState


@dataclass
class RecordButton:
    name: str
    unpressed_color: str
    unpressed_msg: str
    pressed_color: str
    pressed_msg: str
    icon: str
    on_click: Callable
    disabled: bool
    args: tuple[str, ...]

    def __call__(self) -> bool:
        color_key = f"{self.name}_button_color"
        msg_key = f"{self.name}_button_msg"
        is_pressed_now_key = f"{self.name}_button_pressed_now"
        in_pressed_state_key = f"{self.name}_button_pressed_state"
        prev_color = st.session_state.get(color_key, self.unpressed_color)
        prev_msg = st.session_state.get(msg_key, self.unpressed_msg)

        def _on_click():
            st.session_state[color_key] = self.pressed_color
            st.session_state[msg_key] = self.pressed_msg
            st.session_state[is_pressed_now_key] = True
            st.session_state[in_pressed_state_key] = True
            self.on_click(self.args)

        is_pressed = st.session_state.get(is_pressed_now_key, False) | st.button(
            f":{prev_color}-background[:{self.icon}: {prev_msg}]",
            key=f"{self.name}_button",
            on_click=_on_click,
            use_container_width=True,
            disabled=self.disabled,
        )

        st.session_state[is_pressed_now_key] = False
        return is_pressed

    def reset(self):
        color_key = f"{self.name}_button_color"
        msg_key = f"{self.name}_button_msg"
        is_pressed_now_key = f"{self.name}_button_pressed_now"
        in_pressed_state_key = f"{self.name}_button_pressed_state"
        st.session_state[color_key] = self.unpressed_color
        st.session_state[msg_key] = self.unpressed_msg
        st.session_state[is_pressed_now_key] = False
        st.session_state[in_pressed_state_key] = False


@dataclass
class Callbacks:
    expected_keys: set[str] = field(
        default_factory=lambda: {
            "bpm_cb",
            "metronome_cb",
            "beat_sync_cb",
            "record_cb",
            "reset_cb",
            "mix_cb",
        }
    )

    def default(self, key: str):
        assert key in self.expected_keys, f"{key} not expected!"
        st.session_state[key] = True

    def reset_record(self, key: str, record_button: RecordButton):
        assert key in self.expected_keys, f"{key} not expected!"
        st.session_state[key] = True
        record_button.reset()

    def reset(self):
        # TODO: this mechanism is probably not thread safe
        # ie if 2 buttons are pressed at the same time, we probably
        # miss one callback, but it looks to be the best i can do
        # with streamlits design at the moment
        for key in self.expected_keys:
            st.session_state[key] = False

    def update_changes(self, curr_ui_state: UIState):
        curr_ui_state.bpm.has_changed = st.session_state.get("bpm_cb", False)
        curr_ui_state.enable_metronome.has_changed = st.session_state.get(
            "metronome_cb", False
        )
        curr_ui_state.enable_beat_sync.has_changed = st.session_state.get(
            "beat_sync_cb", False
        )
        curr_ui_state.record.has_changed = st.session_state.get("record_cb", False)
        curr_ui_state.reset.has_changed = st.session_state.get("reset_cb", False)
        curr_ui_state.mix.has_changed = st.session_state.get("mix_cb", False)


def sidebar() -> UIState:
    cb = Callbacks()
    with st.sidebar:
        with st.container(border=True):
            # bpm
            bpm = st.number_input(
                "Enter beats per minute (BPM) :drum_with_drumsticks:",
                min_value=0,
                value=None,
                step=10,
                format="%d",
                key="bpm",
                placeholder="None",
                help="Enter an integer value for bpm, for ex. 100",
                on_change=cb.default,
                args=("bpm_cb",),
            )

            # metronome
            enable_metronome = st.toggle(
                "Enable metronome",
                key="enable_metronome",
                help="metronome begins to play at the set bpm (requires bpm to be set)",
                disabled=bpm is None,
                on_change=cb.default,
                args=("metronome_cb",),
            )

            # sync to beat
            enable_beat_sync = st.toggle(
                "Enable sync to beat",
                key="enable_beat_sync",
                help="recorded track is clipped to nearest beat (requires bpm to be set)",
                disabled=bpm is None,
                on_change=cb.default,
                args=("beat_sync_cb",),
            )

        with st.container(border=True):
            record_button = RecordButton(
                name="record",
                unpressed_msg="Start",
                unpressed_color="gray",
                pressed_msg="Recording...",
                pressed_color="red",
                icon="black_circle_for_record",
                disabled=False,
                on_click=cb.default,
                args="record_cb",
            )
            record = record_button()

            reset = st.button(
                f":gray-background[:leftwards_arrow_with_hook: Reset]",
                key="reset_button",
                use_container_width=True,
                disabled=not record,
                on_click=cb.reset_record,
                kwargs={"key": "reset_cb", "record_button": record_button},
            )

            mix = st.button(
                f":gray-background[:fire: Mix]",
                key="mix_button",
                use_container_width=True,
                disabled=not record,
                on_click=cb.reset_record,
                kwargs={"key": "mix_cb", "record_button": record_button},
            )

        ui_state = UIState(
            bpm=MaybeInt(bpm),  # pyright: ignore
            enable_metronome=MaybeBool(enable_metronome),
            enable_beat_sync=MaybeBool(enable_beat_sync),
            record=MaybeBool(record),
            reset=MaybeBool(reset),
            mix=MaybeBool(mix),
        )

        cb.update_changes(ui_state)
        cb.reset()

        return ui_state


@st.cache_resource
def setup() -> Controller:
    max_track_length_seconds = 3 * 60
    controller = Controller.from_defaults(track_length_seconds=max_track_length_seconds)
    controller.speaker.start()
    return controller


def main():
    controller = setup()
    ui_state = sidebar()
    controller.update(ui_state)


if __name__ == "__main__":
    main()
