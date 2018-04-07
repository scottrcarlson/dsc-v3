#!/usr/bin/python
# ----------------------------
# --- DSC2 IO Handler
#----------------------------
import RPi.GPIO as GPIO

# Pin Definitions

# Reference: Raspberry Pi Zero and LL-RXR-27 radio Pinout Diagrams: https://docs.google.com/document/d/1CCm--WU5d0TojT0b95wAke5KnvuqtFVSWwcs-sNXcJo
# Pins 3 and 5 are used for I2C communication with the OLED and RTC
# Pins 8 and 10 are used for serial communication with the radio

  
PIN_KEY_ENTER   = 31 #B
PIN_KEY_LEFT    = 13
PIN_KEY_RIGHT   = 16
PIN_KEY_UP      = 11
PIN_KEY_DOWN    = 15
PIN_KEY_BACK    = 29 #A
PIN_KEY_EXTRA   = 7  #Center
PIN_RADIO_IRQ   = 38
PIN_RADIO_RESET = 40
PIN_NOT_LOW_BATT = 37
PIN_LED_RED = 33
PIN_LED_GREEN = 36
PIN_LED_BLUE = 35
PIN_TILT = 32
PIN_MOTOR_VIBE = 18

PWM_LED_RED = None
PWM_LED_GREEN = None
PWM_LED_BLUE = None


def init():
    global PWM_LED_RED
    global PWM_LED_GREEN
    global PWM_LED_BLUE

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD)
    
    GPIO.setup(PIN_RADIO_IRQ, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(PIN_RADIO_RESET, GPIO.OUT)    
    GPIO.setup(PIN_KEY_ENTER, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_BACK, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_UP, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_LEFT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_KEY_RIGHT, GPIO.IN, pull_up_down=GPIO.PUD_UP)


    GPIO.setup(PIN_TILT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN_NOT_LOW_BATT, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    GPIO.setup(PIN_MOTOR_VIBE, GPIO.OUT) 
    GPIO.setup(PIN_LED_RED, GPIO.OUT) 
    GPIO.setup(PIN_LED_GREEN, GPIO.OUT) 
    GPIO.setup(PIN_LED_BLUE, GPIO.OUT) 

    GPIO.output(PIN_LED_RED, False)
    GPIO.output(PIN_LED_GREEN, False)
    GPIO.output(PIN_LED_BLUE, False)  

    PWM_LED_RED = GPIO.PWM(PIN_LED_RED, 100)
    PWM_LED_GREEN = GPIO.PWM(PIN_LED_GREEN, 100)
    PWM_LED_BLUE = GPIO.PWM(PIN_LED_BLUE, 100)
    PWM_LED_RED.start(0)
    PWM_LED_GREEN.start(0)
    PWM_LED_BLUE.start(0)