#!/usr/bin/python
# ---------------------------------------
# --- Dirt Simple Comms DSCv3 MAIN Thread
#----------------------------------------
import signal
import time
from time import sleep
from radio import Radio
from display import Display
from ui import UI
#from gps import Gps
import iodef
from message import Message
from config import Config
from crypto import Crypto
import subprocess
import logging
import Queue

version = "v0.3.5"
revision = "?"
isRunning = True            #Main Thread Control Bit

radio = None
display = None
ui = None

heartbeat_ui = Queue.Queue()
heartbeat_display = Queue.Queue()
heartbeat_radio = Queue.Queue()
heartbeat_message = Queue.Queue()

def signal_handler(signal, frame): #nicely shut things down
    log.info("[ " + str(signal) + " ] DSCv3 received shutdown signal.")
    radio.stop()
    #gps.stop()
    ui.stop()
    message.stop()
    display.stop()
    global isRunning
    isRunning = False

def get_hg_rev():
    pipe = subprocess.Popen(
        ["hg", "log", "-l", "1", "--template", "{rev}", '/home/dsc/dsc2'], # node is also available
        stdout=subprocess.PIPE
        )
    return pipe.stdout.read()

if __name__ == "__main__":
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)

    fh = logging.FileHandler('/dscdata/dsc.log')
    ch = logging.StreamHandler()
    fh.setLevel(logging.DEBUG)
    ch.setLevel(logging.DEBUG)

    formatter = logging.Formatter('%(asctime)s| %(module)-12s| %(levelname)-8s| %(message)s')
    fh.setFormatter(formatter)
    formatter = logging.Formatter('%(module)-12s| %(levelname)-8s| %(message)s')
    ch.setFormatter(formatter)

    log.addHandler(fh)
    log.addHandler(ch)

    logging.getLogger("ll_ifc").setLevel(logging.WARNING)

    log.info('+----------------------------+')
    log.info("+ Dirt Simple Comms 3 " + version)
    log.info('+----------------------------+')

    for sig in (signal.SIGABRT, signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)

    try:
        with open('rev','r') as f:
            for line in f:
                segs = line.split(':')
                if len(segs) > 2:
                    revision = segs[1].strip()
                    break
    except:
        log.error("REV file missing.")

    #log.debug("hg rev: " + revision)
    
    config = Config()
    
    if config.hw_rev == 1:
        iodef.init()
    else:
        iodef.initv3()

    crypto = Crypto()

    message = Message(crypto, config,heartbeat_message)
    message.start()

    radio = Radio("/dev/serial0",config, message, heartbeat_radio)
    radio.start()

    #add some logic here to spawn if we have GPS unit
    #gps = Gps()
    #gps.start()

    display = Display(message, version, config, revision, heartbeat_display)
    display.start()

    ui = UI(display,message, crypto, radio, config,heartbeat_ui)
    ui.start()
    ui.splash()

    heartbeat_time = time.time()
    while isRunning:
        try:
            if time.time() - heartbeat_time > 30:
                heartbeat_time = time.time()
                try:
                    packet = heartbeat_ui.get_nowait()
                except Queue.Empty: # Thread possibly dead, start re-covery timer and log
                    log.error("UI Thread seems to be dead.")
                try:
                    packet = heartbeat_display.get_nowait()
                except Queue.Empty: # Thread possibly dead, start re-covery timer and log
                    log.error("Display Thread seems to be dead.")
                try:
                    packet = heartbeat_radio.get_nowait()
                except Queue.Empty: # Thread possibly dead, start re-covery timer and log
                    log.error("Radio Thread seems to be dead.")
                try:
                    packet = heartbeat_message.get_nowait()
                except Queue.Empty: # Thread possibly dead, start re-covery timer and log
                  log.error("Message Thread seems to be dead.")

            elif time.time() - heartbeat_time < 0:
                    log.warn("Time changed to past. Re-initializing.")
                    heartbeat_time = time.time()
        except Exception as e:
                log.error(str(e))
        sleep(1)