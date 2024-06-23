import subprocess
from typing import Callable, dataclass_transform
import streamlit as st
from streamlit.type_util import maybe_tuple_to_list
from streamlit_extras.stylable_container import stylable_container
from dataclasses import dataclass, asdict, field
from gpiozero import Button
from threading import Thread
import time
from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx
from streamlit.runtime.scriptrunner import add_script_run_ctx

from app.controller import Controller, MaybeBool, MaybeInt, UIState
from app.notify import notify
from pilooper.constants import MAC_ADDRESS_HEADPHONES, MAC_ADDRESS_SPEAKER


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

    def __post_init__(self):
        self.color_key = f"{self.name}_button_color"
        self.msg_key = f"{self.name}_button_msg"
        self.is_pressed_now_key = f"{self.name}_button_pressed_now"
        self.in_pressed_state_key = f"{self.name}_button_pressed_state"

    def __call__(self) -> bool:
        prev_color = st.session_state.get(self.color_key, self.unpressed_color)
        prev_msg = st.session_state.get(self.msg_key, self.unpressed_msg)

        # note : the reason we have is_pressed_now_key (instead of just reading the state from
        # the button) is : because we bake the msg / color into the name and when we click
        # we modify the msg / color which modifies the button hash : streamlit doesnt know its
        # the same button which changed!
        is_pressed = st.session_state.get(self.is_pressed_now_key, False) | st.button(
            f":{prev_color}-background[:{self.icon}: {prev_msg}]",
            key=f"{self.name}_button",
            on_click=self.on_press,
            use_container_width=True,
            disabled=self.disabled,
        )

        st.session_state[self.is_pressed_now_key] = False
        return is_pressed

    def on_press(self):
        st.session_state[self.color_key] = self.pressed_color
        st.session_state[self.msg_key] = self.pressed_msg
        st.session_state[self.is_pressed_now_key] = True
        st.session_state[self.in_pressed_state_key] = True
        self.on_click(self.args)

    def reset(self):
        st.session_state[self.color_key] = self.unpressed_color
        st.session_state[self.msg_key] = self.unpressed_msg
        st.session_state[self.is_pressed_now_key] = False
        st.session_state[self.in_pressed_state_key] = False


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
            "stop_cb",
            "clip_50_cb",
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
        curr_ui_state.stop.has_changed = st.session_state.get("stop_cb", False)
        curr_ui_state.clip_50.has_changed = st.session_state.get("clip_50_cb", False)


@st.cache_resource
def setup_gpio_callbacks(record: RecordButton, cb: Callbacks):
    ctx = get_script_run_ctx()  # create a context
    assert ctx is not None

    def gpio_cb_record_and_mix():
        print("button press!")
        add_script_run_ctx(None, ctx)
        is_recording = st.session_state.get(record.in_pressed_state_key, False)
        if not is_recording:
            record.on_press()
        else:
            cb.reset_record(key="mix_cb", record_button=record)
            st.session_state["gpio_mix"] = True
        # note : just st.rerun() doesnt work : that just kills the current thread
        # but doesnt seem to notify the st to rerun the ui thread
        notify()

    def gpio_cb_stop():
        print("stop press!")
        add_script_run_ctx(None, ctx)
        cb.reset_record(key="stop_cb", record_button=record)
        st.session_state["gpio_stop"] = True
        notify()

    gpio_record_and_mix = Button(pin=17, pull_up=True, bounce_time=0.1)
    gpio_record_and_mix.when_activated = gpio_cb_record_and_mix
    gpio_record_and_mix.when_deactivated = gpio_cb_record_and_mix
    st.session_state["gpio_record_and_mix_button"] = gpio_record_and_mix

    gpio_stop = Button(pin=23, pull_up=True, bounce_time=0.1)
    gpio_stop.when_activated = gpio_cb_stop
    gpio_stop.when_deactivated = gpio_cb_stop
    st.session_state["gpio_stop_button"] = gpio_stop


def add_updates_from_gpio(ui_state: UIState):
    # note : record is handled in a different way
    ui_state.mix.value |= st.session_state.get("gpio_mix", False)
    ui_state.stop.value |= st.session_state.get("gpio_stop", False)

    # reset gpio flags
    st.session_state["gpio_mix"] = False
    st.session_state["gpio_stop"] = False


def connect_speaker(speaker_choice: str, prev_speaker_choice: str | None):
    mac_addresses = {
        "headphones": MAC_ADDRESS_HEADPHONES,
        "speaker": MAC_ADDRESS_SPEAKER,
    }

    # nothing to do
    if prev_speaker_choice is not None and prev_speaker_choice == speaker_choice:
        return

    # disconnect prev choice
    if prev_speaker_choice is not None:
        if (
            subprocess.call(
                ["bluetoothctl", "disconnect", mac_addresses[prev_speaker_choice]]
            )
            != 0
        ):
            st.toast(f"disconnecting {prev_speaker_choice} failed :(")
            st.session_state["speaker_choice"] = None
            return

    # connect new speaker
    if subprocess.call(["bluetoothctl", "connect", mac_addresses[speaker_choice]]) != 0:
        st.toast(f"switching to {speaker_choice} failed :(")
        st.session_state["speaker_choice"] = None
        return

    st.session_state["speaker_choice"] = speaker_choice


def sidebar() -> UIState:
    cb = Callbacks()
    with st.sidebar:
        with st.container(border=True):
            # bpm
            bpm = st.number_input(
                "Enter beats per minute (BPM) :stopwatch:",
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

            # clip 50
            clip_50 = st.toggle(
                "Enable clip 50%",
                key="clip_50",
                help="recorded track is clipped to first half (to avoid pedal click)",
                on_change=cb.default,
                args=("clip_50_cb",),
            )

        with st.container(border=True):
            options = {
                "headphones": ":headphones: headphones",
                "speaker": ":loud_sound: speaker",
            }
            speaker_choice = st.radio(
                label="Choose output", options=list(options.values())
            )
            match speaker_choice:
                case ":headphones: headphones":
                    speaker_choice = "headphones"
                case ":loud_sound: speaker":
                    speaker_choice = "speaker"
                case _:
                    assert False
            prev_speaker_choice = st.session_state.get("speaker_choice", None)
            connect_speaker(speaker_choice, prev_speaker_choice)
            # note : setting the speaker choice even if the call fails because the radio
            # button gets set anyway

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

            stop = st.button(
                f":gray-background[:x: Stop]",
                key="stop_button",
                use_container_width=True,
                disabled=not record,
                on_click=cb.reset_record,
                kwargs={"key": "stop_cb", "record_button": record_button},
            )

            mix = st.button(
                f":gray-background[:fire: Mix]",
                key="mix_button",
                use_container_width=True,
                disabled=not record,
                on_click=cb.reset_record,
                kwargs={"key": "mix_cb", "record_button": record_button},
            )

            reset = st.button(
                f":gray-background[:arrows_counterclockwise: Reset]",
                key="reset_button",
                use_container_width=True,
                on_click=cb.reset_record,
                kwargs={"key": "reset_cb", "record_button": record_button},
            )

        ui_state = UIState(
            bpm=MaybeInt(bpm),  # pyright: ignore
            enable_metronome=MaybeBool(enable_metronome),
            enable_beat_sync=MaybeBool(enable_beat_sync),
            record=MaybeBool(record),
            stop=MaybeBool(stop),
            reset=MaybeBool(reset),
            mix=MaybeBool(mix),
            clip_50=MaybeBool(clip_50),
        )
        add_updates_from_gpio(ui_state)

        cb.update_changes(ui_state)
        cb.reset()

        setup_gpio_callbacks(record_button, cb)

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
