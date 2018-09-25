#!/usr/bin/python
# ---------------------------------------
# --- Dirt Simple Comms DSCv3 MAIN Thread
# ----------------------------------------
import signal
import logging
import Queue
import RPi.GPIO as GPIO
from time import sleep
import time
import iodef

from message import Message
from crypto import Crypto
from radio import Radio
from display import Display
from ui import UI
from gps import Gps
from config import Config

version = "v0.5.0"
revision = "?"              # grab this from git
isRunning = True            # Main Thread Control Bit

radio = None
display = None
ui = None

heartbeat_ui = Queue.Queue()
heartbeat_display = Queue.Queue()
heartbeat_radio = Queue.Queue()
heartbeat_message = Queue.Queue()


def signal_handler(signal, frame):  # nicely shut things down
    quitdsc()


def quitdsc():
    log.info("DSC received shutdown signal")
    radio.stop()
    gps.stop()
    message.test_message_file.close()
    message.stop()

    if config.hw_rev < 3:
        ui.stop()
        display.stop()
    global isRunning

    isRunning = False


if __name__ == "__main__":
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler('/dscdata/dsc.log')
    ch = logging.StreamHandler()
    fh.setLevel(logging.DEBUG)
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s| %(module)-12s| %(levelname)-8s| %(message)s')
    fh.setFormatter(formatter)
    formatter = logging.Formatter('%(asctime)s| %(module)-12s| %(levelname)-8s| %(message)s')
    ch.setFormatter(formatter)

    log.addHandler(fh)
    log.addHandler(ch)

    logging.getLogger("ll_ifc").setLevel(logging.WARNING)

    log.info('+----------------------------+')
    log.info("+ Dirt Simple Comms 4 " + version)
    log.info('+----------------------------+')


    # log.debug("hg rev: " + revision)
  
    config = Config()
    log.info("HW Rev: " + str(config.hw_rev))
    log.debug("Node UID: " + config.node_uuid)
    iodef.init()

    if config.hw_rev >= 3:
        import ble
        import ble_gatt_dsc as ble_gatt
        ble.init_ble()

    crypto = Crypto()

    message = Message(crypto, config, heartbeat_message)
    message.start()

    radio = Radio("/dev/serial0", config, message, heartbeat_radio)
    radio.start()

    gps = Gps()
    gps.start()

    if config.hw_rev < 3:
        display = Display(message, version, config, revision, heartbeat_display)
        display.start()

        ui = UI(display, message, crypto, radio, config, heartbeat_ui)
        ui.start()
        ui.splash()

    if config.hw_rev >= 3:
        dscGatt = ble_gatt.DscGatt(quitdsc, message, config, radio)
        dscGatt.start()

    """
    GPIO.output(iodef.PIN_MOTOR_VIBE, True)
    sleep(0.3)
    GPIO.output(iodef.PIN_MOTOR_VIBE, False)
    sleep(0.1)
    GPIO.output(iodef.PIN_MOTOR_VIBE, True)
    sleep(0.3)
        GPIO.output(iodef.PIN_MOTOR_VIBE, False)
    """
    heartbeat_time = time.time()

    log.debug("HELLO Have we returned control?")
    for sig in (signal.SIGABRT, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)

    while isRunning:
        try:
            if time.time() - heartbeat_time > 30:
                heartbeat_time = time.time()

                if not GPIO.input(iodef.PIN_NOT_LOW_BATT):
                    log.info("Low Battery")
                    log.info("Shutting the system down in 60 seconds.")
                    # Shutdown timer --> do it

                # if GPIO.input(iodef.PIN_TILT):
                #    log.info("Tilted.")
                # else:
                #    log.info("Not Tilted.")
                if config.hw_rev < 3:
                    try:
                        packet = heartbeat_ui.get_nowait()
                    except Queue.Empty:  # Thread possibly dead, start re-covery timer and log
                        log.error("UI Thread seems to be dead.")
                    try:
                        packet = heartbeat_display.get_nowait()
                    except Queue.Empty:  # Thread possibly dead, start re-covery timer and log
                        log.error("Display Thread seems to be dead.")
                try:
                    packet = heartbeat_radio.get_nowait()
                except Queue.Empty:  # Thread possibly dead, start re-covery timer and log
                    log.error("Radio Thread seems to be dead.")
                try:
                    packet = heartbeat_message.get_nowait()
                except Queue.Empty:  # Thread possibly dead, start re-covery timer and log
                    log.error("Message Thread seems to be dead.")

            elif time.time() - heartbeat_time < 0:
                    log.warn("Time changed to past. Re-initializing.")
                    heartbeat_time = time.time()
        except Exception as e:
                log.error(str(e))
        sleep(1)
    iodef.PWM_LED_RED.stop()
    iodef.PWM_LED_GREEN.stop()
    iodef.PWM_LED_BLUE.stop()
