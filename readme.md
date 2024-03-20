# pi_looper : a guitar loop pedal for the raspberry pi 

this project implements an acoustic guitar looper pedal built for the raspberry pi-5. guitar loopers typically work with electric / semi-acoustics which have an electrical out. the looper records this electrical out and allows you to play it back while recording a second track over it. if you have a pure acoustic, to my knowledge, theres no convinent way to hook up a loop pedal to it. 

the way it works is as follows : 
- connect the usb microphone and headphones to the raspberry pi
- hit record -> record a track -> stop record
- the recorded track plays back on the headphones
- hit record -> record a second track -> stop record
- mixed tracks 1 and 2 play on the headphones
- and so on...

## what do i need?
to use this project, you will need : 
- a raspberry pi (5)
- a usb microphone
- a pair of headphones
- an acoustic guitar
- know how to play that guitar

## setup

### install dependencies
```
sudo apt-get install portaudio19-dev python<xxx>-dev
```
setup the virtual env: 
```
scripts/venv-sync
```
