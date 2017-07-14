#!/usr/bin/python
# ----------------------------
# --- DSC2 IO Handler
#----------------------------
import RPi.GPIO as GPIO

# Pin Definitions

# Reference: Raspberry Pi Zero and LL-RXR-27 radio Pinout Diagrams: https://docs.google.com/document/d/1CCm--WU5d0TojT0b95wAke5KnvuqtFVSWwcs-sNXcJo
# Pins 3 and 5 are used for I2C communication with the OLED and RTC
# Pins 8 and 10 are used for serial communication with the radio
PIN_RADIO_IRQ   = 7  #
PIN_RADIO_RESET = 40 # 
PIN_OLED_RESET  = 11
PIN_KEY_ENTER   = 36
PIN_KEY_BACK    = 35
PIN_KEY_LEFT    = 29
PIN_KEY_RIGHT   = 38
PIN_KEY_UP      = 33
PIN_KEY_DOWN    = 37

def init():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    
    GPIO.setup(PIN_RADIO_IRQ, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_RADIO_RESET, GPIO.OUT)    
    GPIO.setup(PIN_OLED_RESET, GPIO.OUT)
    GPIO.setup(PIN_KEY_ENTER, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_BACK, GPIO.IN, pull_up_down=GPIO.PUD_OFF)
    GPIO.setup(PIN_KEY_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_LEFT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_RIGHT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.output(PIN_OLED_RESET, True)
