from typing import Callable, dataclass_transform
import streamlit as st
from streamlit.type_util import maybe_tuple_to_list
from streamlit_extras.stylable_container import stylable_container
from dataclasses import dataclass


@dataclass
class Button:
    name: str
    unpressed_color: str
    unpressed_msg: str
    pressed_color: str
    pressed_msg: str
    icon: str
    on_click: Callable | None
    disabled: bool

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
            if self.on_click:
                self.on_click()

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


def sidebar():
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
            )

            # metronome
            enable_metronome = st.toggle(
                "Enable metronome",
                key="enable_metronome",
                help="metronome begins to play at the set bpm (requires bpm to be set)",
                disabled=bpm is None,
            )

            # sync to beat
            enable_beat_sync = st.toggle(
                "Enable sync to beat",
                key="enable_beat_sync",
                help="recorded track is clipped to nearest beat (requires bpm to be set)",
                disabled=bpm is None,
            )

        with st.container(border=True):
            record_button = Button(
                name="record",
                unpressed_msg="Start",
                unpressed_color="gray",
                pressed_msg="Recording...",
                pressed_color="red",
                icon="black_circle_for_record",
                on_click=None,
                disabled=False,
            )
            record = record_button()

            reset = st.button(
                f":gray-background[:leftwards_arrow_with_hook: Reset]",
                key="reset_button",
                on_click=record_button.reset,
                use_container_width=True,
                disabled=not record,
            )

            mix = st.button(
                f":gray-background[:fire: Mix]",
                key="mix_button",
                on_click=record_button.reset,
                use_container_width=True,
                disabled=not record,
            )


def main():
    sidebar()


if __name__ == "__main__":
    main()
