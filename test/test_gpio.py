from gpiozero import Button

from typer import Typer
import time

app = Typer()


@app.command()
def button_test():
    def button_cb():
        print("button pressed!")

    b = Button(pin=17, pull_up=True, bounce_time=0.1)
    b.when_activated = button_cb
    b.when_deactivated = button_cb
    time.sleep(10)


if __name__ == "__main__":
    app()
