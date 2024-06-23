# pi_looper : a guitar loop pedal for the raspberry pi 

| [![Watch the video](https://img.youtube.com/vi/JfG4PdhbKrM/maxresdefault.jpg)](https://www.youtube.com/watch?v=JfG4PdhbKrM) |
|:--:| 
| *Click ☝️for video* |

this project implements an acoustic guitar looper pedal built for the raspberry pi-5. guitar loopers typically work with electric / semi-acoustics which have an electrical out. the looper records this electrical out and allows you to play it back while recording a second track over it. if you have a pure acoustic, one could try doing these things with garage-band and a mic, but operating it with a mouse is simply pathetic and im not sure how easy it is to hook up garage-band to a foot pedal. more importantly doing it on a r-pi with your own code is so much cooler. 

the way this works is as follows : 
- connect a usb microphone and headphones to the raspberry pi
- hit record -> record a track -> stop record
- the recorded track plays back on the headphones
- hit record -> record a second track -> stop record
- mixed tracks 1 and 2 play on the headphones
- and so on...

## what you need
to use this project, you will need : 
- a raspberry pi (5) running ubuntu23.10
- a usb microphone
- a pair of headphones
- [6.3mm guitar socket] (https://www.thomann.de/at/adam_hall_klinkenbuchse_7217pcb02_pack.htm)
- a foot-pedal (the one i use is : LeadFoot FS-2)
- a breadboard and some jumper cables
- an acoustic guitar
- know how to play that guitar

## setup
![IMG_9195](https://github.com/acharyahemanth/pi_looper/assets/12888666/51a3965e-3206-483f-b2a6-e8006bd2bf57)
- connect USB mic to the r-pi
- mount the guitar socket on the breadboard.
- connect gpio pins 17 to the pin corresponding to switch-1
- connect gpio pins 23 to the pin corresponding to switch-2
- connect one of the ground gpio pins to the ground pin of the socket
- connect the foot-pedal's guitar cable to the socket

Note : 
- gpios are configurable in the code
- the code uses internal pull-up resistors on the gpio pins, hence no external resistors are required

### install dependencies
```
sudo apt-get install portaudio19-dev python3.11-dev
```
setup the virtual env: 
```
scripts/venv-sync
```
