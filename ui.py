#!/usr/bin/python
# ----------------------------
# --- DSC3 UI THREAD
#----------------------------
import time
from time import sleep
import RPi.GPIO as GPIO
import iodef
from oled.device import ssd1306, sh1106
from oled.render import canvas
from PIL import ImageDraw, Image, ImageFont
from threading import *
import os
import screen as scr
import logging

#DISPLAY MODES
m_MAIN_MENU = 6
m_COMPOSE = 5
m_SPLASH = 2
m_MSG_VIEWER = 8


m_IDLE = 0
m_LOCK = 1
m_SPARE3 = 3
m_COMPOSE_MENU = 4
m_DIALOG = 7
m_DIALOG_YESNO = 9
m_DIALOG_TASK = 11
m_REG = 12
m_STATUS = 13
#m_STATUS_LASTSEEN = 14

#DIALOG COMMAND (If Yes is Chosen)
cmd_SHUTDOWN = 0
cmd_GEN_KEYSET = 1
cmd_FACTORY_RESET = 2
cmd_SOFTWARE_UPDATE = 3
cmd_IMPORT_PUB_KEYS = 4
cmd_EXPORT_PUB_KEYS = 5
cmd_WIPE_USB_DRV = 6

keyboard = "abcdefghijklmnopqrstuvwxyz1234567890!?$%.-"

class UI(Thread):
    def __init__(self, display, message, crypto, config):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger(self.__class__.__name__)
        GPIO.add_event_detect(iodef.PIN_KEY_UP, GPIO.FALLING, callback=self.key_up, bouncetime=40)
        GPIO.add_event_detect(iodef.PIN_KEY_DOWN, GPIO.FALLING, callback=self.key_down, bouncetime=40)
        GPIO.add_event_detect(iodef.PIN_KEY_LEFT, GPIO.FALLING, callback=self.key_left, bouncetime=40)
        GPIO.add_event_detect(iodef.PIN_KEY_RIGHT, GPIO.FALLING, callback=self.key_right, bouncetime=40)
        GPIO.add_event_detect(iodef.PIN_KEY_ENTER, GPIO.FALLING, callback=self.key_enter, bouncetime=40)
        GPIO.add_event_detect(iodef.PIN_KEY_BACK, GPIO.RISING, callback=self.key_back, bouncetime=40)

        self.display = display
        self.crypto = crypto
        self.message = message
        self.config = config

        self.is_idle = False

        self.lock()
        self.log.info("Initialized UI Thread.")

    def run(self):
        self.event.wait(1)
        while not self.event.is_set():
            if self.is_idle:
                self.idle()
                self.is_idle = False
            else:
                self.is_idle = True

            self.event.wait(5)

    def stop(self):
        self.log.info("Stopping UI Thread.")
        self.event.wait(2)
        self.event.set()

    def idle(self):
        if self.display.mode == m_LOCK:
            self.display.mode = m_IDLE
        elif self.display.mode == m_MAIN_MENU:
            self.display.mode = m_IDLE

    def lock(self):  #Key removed, clear any relevant data
        self.message.compose_msg = ""
        self.display.mode = m_LOCK

    def splash(self):
        self.display.mode = m_SPLASH

    def main_menu(self):
        self.display.row_index = 0
        self.display.mode = m_MAIN_MENU

    def create_msg(self, msg):
        if self.display.mode != m_COMPOSE and self.display.mode != m_IDLE:
            self.message.compose_msg = msg
            self.display.mode = m_COMPOSE
            self.display.row_index = 0
            self.display.col_index = 0
            return True
        return False

    def key_up(self, channel):
        self.is_idle = False
        #self.display.key_up()
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
            self.display.mode = m_STATUS
        elif self.display.mode == m_COMPOSE or self.display.mode == m_REG:
            if self.display.row_index == 1:
                self.display.row_index = 0
            else:
                self.display.row_index = -1
                self.display.col_index = 0
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_MAIN_MENU:
            self.display.row_index -= 1
            if self.display.row_index < 0:
                self.display.row_index = 0
        elif self.display.mode == m_COMPOSE_MENU:
            self.display.row_index -= 1
            if self.display.row_index < 0:
                self.display.row_index = 0
        elif self.display.mode == m_MSG_VIEWER:
            self.display.row_index -= 5
            if self.display.row_index < 0:
                self.display.row_index = 0

    def key_down(self, channel):
        self.is_idle = False
        ##print "pressed DOWN Key."
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_COMPOSE or self.display.mode == m_REG:
            self.display.row_index += 1
            if self.display.row_index > 1:
                self.display.row_index = 1
        elif self.display.mode == m_MAIN_MENU:
            self.display.row_index += 1
            if self.display.row_index >= len(scr.main_menu):
                self.display.row_index = len(scr.main_menu) -1
        elif self.display.mode == m_COMPOSE_MENU:
            self.display.row_index += 1
            if self.display.row_index >= len(scr.compose_menu):
                self.display.row_index = len(scr.compose_menu) -1
        elif self.display.mode == m_MSG_VIEWER:
            self.display.row_index += 5
            if self.display.row_index >= len(self.message.group_cleartexts):
                self.display.row_index = len(self.message.group_cleartexts) -1

    def key_left(self, channel):
        self.is_idle = False
        ##print "pressed LEFT Key."
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_COMPOSE or self.display.mode == m_REG:
            self.display.col_index -= 1
            if self.display.row_index == -1:
                if self.display.col_index < 0:
                    self.display.col_index = 0
            elif self.display.col_index < 0:
                self.display.col_index = 20
                if self.display.row_index == 1:
                    self.display.row_index = 0
                else:
                    self.display.row_index = 1
        elif self.display.mode == m_DIALOG_YESNO:
            self.display.col_index -= 1
            if self.display.col_index < 0:
                self.display.col_index = 0
        
    def key_right(self, channel):
        self.is_idle = False
        ##print "pressed RIGHT Key."
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_COMPOSE or self.display.mode == m_REG:
            self.display.col_index += 1
            if self.display.row_index == -1:
                if self.display.col_index > 3:
                    self.display.col_index = 3
            elif self.display.col_index > 20:
                self.display.col_index = 0
                if self.display.row_index == 0:
                    self.display.row_index = 1
                else:
                    self.display.row_index = 0
        elif self.display.mode == m_DIALOG_YESNO:
            self.display.col_index += 1
            if self.display.col_index > 1:
                self.display.col_index = 1

    #self.display.dialog_msg = "Keyset Generated!"
    #self.display.dialog_msg2 = "Test yubikey password"
    #self.display.dialog_msg3 = "==[Press Yubikey]=="
    #self.display.dialog_cmd = cmd_GEN_KEYSET 
    #self.display.row_index = 0
    #self.display.col_index = 0
    #self.display.dialog_task_done = False
    #self.display.dialog_next_mode = m_MAIN_MENU
    #self.display.mode = m_DIALOG_TASK
                    
    def key_enter(self, channel):
        self.is_idle = False
        ###print "pressed ENTER Key."
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_REG:
            if self.display.row_index >= 0:
                index = (self.display.row_index * 21) + self.display.col_index
                if len(self.config.alias) < 12:
                    self.config.alias = self.config.alias + keyboard[index:index+1]
            else:
                if self.display.col_index == 0:
                    self.display.dialog_msg = "Hello " + self.config.alias + "!"
                    self.display.row_index = 0
                    self.display.col_index = 0
                    self.config.save_config(True)
                    self.display.dialog_msg2 = "Generating Keyset"
                    self.display.dialog_msg3 = "Please wait..."
                    self.display.dialog_task_done = False
                    self.display.dialog_next_mode = m_MAIN_MENU
                    self.display.mode = m_DIALOG_TASK
                    self.event.wait(0.5)
                    password = self.crypto.generate_random_password(38)
                    sig_pass =str(password)[:len(password)/2]
                    crypt_pass = str(password)[len(password)/2:]
                    if self.crypto.gen_keysets(crypt_pass,sig_pass,self.config.alias):
                        #self.yubikey.set_slot1(password)
                        self.display.dialog_msg = "Keyset Generated!"
                        self.display.dialog_msg2 = "Test yubikey password"
                        self.display.dialog_msg3 = "==[Press Yubikey]=="
                        self.display.dialog_cmd = cmd_GEN_KEYSET
                    else:
                        self.display.dialog_msg = "Err: Gen Keysets"
                        self.display.dialog_msg2 = "Keyset Already Exists"
                        self.display.dialog_msg3 = "==[Press any key]=="
                        self.display.mode = m_DIALOG
                    password = "" # Unneccessary!?

        elif self.display.mode == m_COMPOSE:
            if self.display.row_index >= 0:
                index = (self.display.row_index * 21) + self.display.col_index
                self.message.compose_msg = self.message.compose_msg + keyboard[index:index+1]
            else:
                if self.display.col_index == 0:
                    self.display.dialog_msg = "Message Sent!"
                    self.display.dialog_msg3 = "==[Press AnyKey]=="
                    self.message.process_composed_msg(self.message.compose_msg)
                    self.display.row_index = 0
                    self.display.col_index = 0
                    self.display.mode = m_DIALOG
                elif self.display.col_index == 1:
                    self.message.compose_msg += " "
                elif self.display.col_index == 2:
                    self.message.compose_msg = ""
                elif self.display.col_index == 3:
                    self.message.compose_msg = ""
                    self.main_menu()
        elif self.display.mode == m_MSG_VIEWER:
            self.log.debug("User Updating Msg Thread.")

        elif self.display.mode == m_COMPOSE_MENU:
            self.message.compose_msg = scr.compose_menu[self.display.row_index]
            self.display.row_index = 0
            self.display.col_index = 0
            self.display.mode = m_COMPOSE
        elif self.display.mode == m_MAIN_MENU:
            self.log.debug( "MainMenu Selected: " +scr.main_menu[self.display.row_index])
            if self.display.row_index == 0:
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.mode = m_COMPOSE_MENU
            elif self.display.row_index == 1:
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.dialog_next_mode = m_MAIN_MENU
                self.display.mode = m_MSG_VIEWER
            elif self.display.row_index == 2:
                self.display.mode = m_STATUS
            elif self.display.row_index == 4:
                self.display.dialog_cmd = cmd_SHUTDOWN
                self.display.dialog_msg = "Shutdown?"
                self.display.dialog_msg2 = "Are you not entertained?"
                self.display.col_index = 0
                self.display.mode = m_DIALOG_YESNO
        elif self.display.mode == m_DIALOG_YESNO:
            if self.display.col_index == 1:
                pass
            else:
                pass

    def key_back(self, channel):
        self.is_idle = False
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_MAIN_MENU:
            self.display.mode = m_STATUS
        elif self.display.mode == m_STATUS:
            self.display.mode = m_MAIN_MENU
        elif self.display.mode == m_COMPOSE:
            self.message.compose_msg = self.message.compose_msg[:-1]
        elif self.display.mode == m_REG:
            self.config.alias = self.config.alias[:-1]
        else:
            self.display.row_index = 0
            self.display.col_index = 0
            self.display.dialog_next_mode = m_MAIN_MENU
            self.display.mode = m_MAIN_MENU