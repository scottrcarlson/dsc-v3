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
import Queue
import subprocess

#DISPLAY MODES
m_MAIN_MENU = 6
m_COMPOSE = 5
m_SPLASH = 2
m_MSG_VIEWER = 8
m_SETTINGS = 1
m_LOG_VIEWER = 3

m_IDLE = 0
m_LOCK = 1
m_COMPOSE_MENU = 4
m_DIALOG = 7
m_DIALOG_YESNO = 9
m_DIALOG_TASK = 11
m_REG = 12
m_STATUS = 13
#m_STATUS_LASTSEEN = 14

#DIALOG COMMAND (If Yes is Chosen)
cmd_SHUTDOWN = 0
cmd_CLEARMSGS = 1
cmd_MANUALSYNCCLK = 2

keyboard = "abcdefghijklmnopqrstuvwxyz1234567890!?$%.-"

class UI(Thread):
    def __init__(self, display, message, crypto, config, heartbeat):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()
        #self.log.setLevel(logging.INFO)

        self.heartbeat = heartbeat

        self.active_high = True
        bounce_time = 80
        if config.hw_rev != 1:
            bounce_time = 175 #HW Rev2 has no hardware debouncing
            self.active_high = False

        GPIO.add_event_detect(iodef.PIN_KEY_UP, GPIO.FALLING, callback=self.key_up, bouncetime=bounce_time)
        GPIO.add_event_detect(iodef.PIN_KEY_DOWN, GPIO.FALLING, callback=self.key_down, bouncetime=bounce_time)
        GPIO.add_event_detect(iodef.PIN_KEY_LEFT, GPIO.FALLING, callback=self.key_left, bouncetime=bounce_time)
        GPIO.add_event_detect(iodef.PIN_KEY_RIGHT, GPIO.FALLING, callback=self.key_right, bouncetime=bounce_time)
        GPIO.add_event_detect(iodef.PIN_KEY_ENTER, GPIO.FALLING, callback=self.key_enter, bouncetime=bounce_time)
        if config.hw_rev == 1:
            GPIO.add_event_detect(iodef.PIN_KEY_BACK, GPIO.RISING, callback=self.key_back, bouncetime=bounce_time)
        else:
            GPIO.add_event_detect(iodef.PIN_KEY_BACK, GPIO.FALLING, callback=self.key_back, bouncetime=bounce_time)

        self.display = display
        self.crypto = crypto
        self.message = message
        self.config = config

        self.is_idle = False

        self.key_repeat = -1 # -1/None 0/Left 1/Right
        self.key_repeat_rate = 0.08
        self.key_repeat_delay = 0.5
        self.lock()
        self.log.info("Initialized UI Thread.")

    def run(self):
        self.event.wait(1)
        key_repeat_time = 0
        key_delay_time = 0
        heartbeat_time = 0
        idle_time = 0
        while not self.event.is_set():
            try:
                if time.time() - heartbeat_time > 5:
                    heartbeat_time = time.time()
                    if self.heartbeat.qsize() == 0:
                        self.heartbeat.put_nowait("hb")
                elif time.time() - heartbeat_time < 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        heartbeat_time = time.time()    

                try:
                    if time.time() - idle_time > 15:
                        idle_time = time.time()
                        if self.is_idle:
                            self.idle()
                            self.is_idle = False
                        else:
                            self.is_idle = True
                    elif time.time() - idle_time < 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        idle_time = time.time()
                except Exception as e:
                    self.log.error(str(e))

                if self.key_repeat == -1:
                    key_delay_time = time.time()

                if time.time() - key_repeat_time > self.key_repeat_rate:
                    key_repeat_time = time.time()
                    if time.time() - key_delay_time > self.key_repeat_delay:
                        if self.key_repeat == 1: #Left Key Repeat
                            if GPIO.input(iodef.PIN_KEY_LEFT) == self.active_high:
                                self.display.key_repeating = True
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
                            else:
                                self.display.key_repeating = False
                                self.key_repeat = -1
                        elif self.key_repeat == 2: #Right Key Repeat
                            if GPIO.input(iodef.PIN_KEY_RIGHT) == self.active_high:
                                self.display.key_repeating = True
                                self.display.col_index += 1
                                if self.display.row_index == -1:
                                    if self.display.col_index > 1:
                                        self.display.col_index = 1
                                elif self.display.col_index > 20:
                                    self.display.col_index = 0
                                    if self.display.row_index == 0:
                                        self.display.row_index = 1
                                    else:
                                        self.display.row_index = 0
                            else:
                                self.display.key_repeating = False
                                self.key_repeat = -1
                elif time.time() - key_repeat_time< 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        key_repeat_time = time.time()    

            except Exception as e:
                self.log.error("Exception: " + str(e))
            self.event.wait(0.05)

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

    def reg(self): 
        self.display.mode = m_REG

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
            self.display.row_index -= 1
            if self.display.row_index < 0:
                self.display.row_index = 0
        elif self.display.mode == m_SETTINGS:
            self.display.row_index -= 1
            if self.display.row_index < 1:
                self.display.row_index = 1

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
            self.display.row_index += 1
            if self.display.row_index >= len(self.message.group_cleartexts):
                self.display.row_index = len(self.message.group_cleartexts) -1
        elif self.display.mode == m_SETTINGS:
            self.display.row_index += 1
            if self.display.row_index > 4:
                self.display.row_index = 4

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
            self.key_repeat = 1 #Actuate Key Repeating
        elif self.display.mode == m_DIALOG_YESNO:
            self.display.col_index -= 1
            if self.display.col_index < 0:
                self.display.col_index = 0
        elif self.display.mode == m_SETTINGS:
            if self.display.row_index == 1:
                self.config.tdma_total_slots -= 1
                if self.config.tdma_total_slots < 2: #Whats the point if not at least 2?!
                    self.config.tdma_total_slots = 2
            elif self.display.row_index == 2:
                self.config.tdma_slot -= 1
                if self.config.tdma_slot < 0:
                    self.config.tdma_slot = 0
            elif self.display.row_index == 3:
                self.config.tx_time -= 1
                if self.config.tx_time < 1:
                    self.config.tx_time = 1
            elif self.display.row_index == 4:
                self.config.tx_deadband -= 1
                if self.config.tx_deadband < 1:
                    self.config.tx_deadband = 1
        
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
                if self.display.col_index > 1:
                    self.display.col_index = 1
            elif self.display.col_index > 20:
                self.display.col_index = 0
                if self.display.row_index == 0:
                    self.display.row_index = 1
                else:
                    self.display.row_index = 0
            self.key_repeat = 2 #Actuate Key Repeating
        elif self.display.mode == m_DIALOG_YESNO:
            self.display.col_index += 1
            if self.display.col_index > 1:
                self.display.col_index = 1
        elif self.display.mode == m_SETTINGS:
            if self.display.row_index == 1:
                self.config.tdma_total_slots += 1
            elif self.display.row_index == 2:
                self.config.tdma_slot += 1
            elif self.display.row_index == 3:
                self.config.tx_time += 1
            elif self.display.row_index == 4:
                self.config.tx_deadband += 1

    #self.display.dialog_msg = "Main Dialog Msg"
    #self.display.dialog_msg2 = "Line2"
    #self.display.dialog_msg3 = "Line3"
    #self.display.dialog_cmd = cmd_SOME_TASK_TO_PERFORM 
    #self.display.row_index = 0 #Track Menu Item Selected
    #self.display.col_index = 0 #Track Menu Item Selected
    #self.display.dialog_task_done = False #Task Complete Flag
    #self.display.mode = m_DIALOG_TASK #Next Mode to Enter
    #self.display.dialog_next_mode = m_MAIN_MENU #Where to go after the next mode
                    
    def key_enter(self, channel):
        self.is_idle = False
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_REG:
            if self.display.row_index >= 0:
                index = (self.display.row_index * 21) + self.display.col_index
                if self.display.reg_stage == 1:
                    if len(self.message.alias) < 8:
                        self.message.alias = self.message.alias + keyboard[index:index+1]
                elif self.display.reg_stage == 2:
                    if len(self.message.network_key) < 16:
                        self.message.network_key = self.message.network_key + keyboard[index:index+1]
                elif self.display.reg_stage == 3:
                    if len(self.message.alias) < 16:
                        self.message.group_key = self.message.group_key + keyboard[index:index+1]

            else:
                if self.display.col_index == 0: # NEXT Field
                    self.display.reg_stage += 1
                    if self.display.reg_stage > 4:
                        self.display.reg_stage = 1

                elif self.display.col_index == 1: # DONE. Register node.
                    if self.display.reg_stage == 4:
                        self.display.row_index = 0
                        self.display.col_index = 0
                        self.display.dialog_task_done = False
                         
                        #Pad the keys. Not a great idea. Need to improve this for lazy people.
                        #Key size has to be 16bytes
                        self.message.alias = self.message.alias.ljust(8)
                        self.message.network_key = self.message.network_key.ljust(16)
                        self.message.group_key = self.message.group_key.ljust(16)

                        self.message.node_registered = True
                        self.display.mode = m_MAIN_MENU

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
            self.log.debug("User Clear Msg Request.")
            self.display.dialog_cmd = cmd_CLEARMSGS
            self.display.dialog_msg = "Clear Messages"
            self.display.dialog_msg2 = "Are you sure?"
            self.display.col_index = 0
            self.display.dialog_next_mode = m_MSG_VIEWER
            self.display.mode = m_DIALOG_YESNO
        elif self.display.mode == m_STATUS:
            self.log.debug("User Manual Sync Clock Request.")
            self.display.dialog_cmd = cmd_MANUALSYNCCLK
            self.display.dialog_msg = "Manual Clk Sync?"
            self.display.dialog_msg2 = "Are you sure?"
            self.display.col_index = 0
            self.display.dialog_next_mode = m_MAIN_MENU
            self.display.mode = m_DIALOG_YESNO
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
            elif self.display.row_index == 3:
                self.display.col_index = 0
                self.display.row_index = 1
                self.display.mode = m_SETTINGS
            elif self.display.row_index == 4:
                self.display.mode = m_LOG_VIEWER
            elif self.display.row_index == 5:
                self.display.dialog_cmd = cmd_SHUTDOWN
                self.display.dialog_msg = "Shutdown?"
                self.display.dialog_msg2 = "Are you sure?"
                self.display.col_index = 0
                self.display.mode = m_DIALOG_YESNO
        elif self.display.mode == m_DIALOG_YESNO:
            if self.display.col_index == 1: #Yes Chosen
                if self.display.dialog_cmd == cmd_SHUTDOWN:
                    self.display.dialog_msg = "DSCv3"
                    self.display.dialog_msg2 = "Shutting Down."
                    self.display.dialog_task_done = False
                    self.display.mode = m_DIALOG_TASK
                    os.system("sudo shutdown -h now")
                elif self.display.dialog_cmd == cmd_CLEARMSGS:
                    self.message.network_plaintexts = []
                    self.display.mode = m_MSG_VIEWER
                elif self.display.dialog_cmd == cmd_MANUALSYNCCLK:
                    pipe = subprocess.Popen(
                                ["sudo", "date", '-s', "07/30/17 00:00:00"], # node is also available
                                stdout=subprocess.PIPE
                                )
                    pipe = subprocess.Popen(
                                ["sudo", "hwclock", '-w'], # node is also available
                                stdout=subprocess.PIPE
                                )
                    self.display.mode = self.display.dialog_next_mode
            else:
                self.display.mode = self.display.dialog_next_mode

    def key_back(self, channel):
        self.is_idle = False
        if self.display.mode == m_IDLE:
            self.display.mode = m_STATUS
        elif self.display.mode == m_DIALOG:
            self.display.dialog_confirmed = True
        elif self.display.mode == m_MAIN_MENU:
            #self.display.mode = m_STATUS
            pass
        elif self.display.mode == m_STATUS:
            self.display.mode = m_MAIN_MENU
        elif self.display.mode == m_COMPOSE:
            self.message.compose_msg = self.message.compose_msg[:-1]
        elif self.display.mode == m_SETTINGS:
            self.config.save_config(True)
            self.main_menu();
        elif self.display.mode == m_LOG_VIEWER:
            self.main_menu();
        elif self.display.mode == m_REG:
            if self.display.reg_stage == 1:
                self.message.alias = self.message.alias[:-1]
            elif self.display.reg_stage == 2:
                self.message.network_key = self.message.network_key[:-1]
            elif self.display.reg_stage == 3:
                self.message.group_key = self.message.group_key[:-1]
        else:
            self.display.row_index = 0
            self.display.col_index = 0
            self.display.dialog_next_mode = m_MAIN_MENU
            self.display.mode = m_MAIN_MENU