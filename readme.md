# pi_looper : a raspberry pi based guitar looper

## what is this?

this project implements an acoustic guitar looper pedal built for the raspberry pi-5. guitar loopers typically work with electric / semi-acoustics which have an electrical out. the looper records this electrical out and allows you to play it back while recording a second track over it. if you have a pure acoustic guitar, to my knowledge, theres no convinent way to hook up a loop pedal to it. 

to use this project, you will need : 
- a raspberry pi-5
- a USB microphone
- a pair of headphones
- an acoustic guitar
- know how to play that guitar - otherwise you have bigger problems to fix

the way it works is as follows : 
- connect the usb microphone and headphones to the raspberry pi
- hit record -> record a track -> stop record
- the recorded track plays back on the headphones
- hit record -> record a second track -> ...
