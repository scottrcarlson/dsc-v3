#!/usr/bin/python
# ----------------------------
# --- DSC2 UI THREAD
#----------------------------
from time import sleep
import time
import RPi.GPIO as GPIO
import iodef
from threading import *
from yubikey import Yubikey
#from display import Display
from oled.device import ssd1306, sh1106
from oled.render import canvas
from PIL import ImageDraw, Image, ImageFont
import os
import screen as scr
import logging

#DISPLAY MODES
m_IDLE = 0
m_LOCK = 1
m_AUTH = 2
m_SPARE3 = 3
m_COMPOSE_MENU = 4
m_COMPOSE = 5
m_MAIN_MENU = 6
m_DIALOG = 7
m_MSG_VIEWER = 8
m_DIALOG_YESNO = 9
m_SYSTEM_MENU = 10
m_DIALOG_TASK = 11
m_REG = 12
m_STATUS = 13
m_STATUS_LASTSEEN = 14

#DIALOG COMMAND (If Yes is Chosen)
cmd_SHUTDOWN = 0
cmd_GEN_KEYSET = 1
cmd_FACTORY_RESET = 2
cmd_SOFTWARE_UPDATE = 3
cmd_IMPORT_PUB_KEYS = 4
cmd_EXPORT_PUB_KEYS = 5
cmd_WIPE_USB_DRV = 6

keyboard = "abcdefghijklmnopqrstuvwxyz1234567890!?$%.-"


view_msg_thread_menu = { # (*) indicates unread messages
    0:"(*)Everyone",
    1:"Doris",
    2:"(*)Boris",
}

test_msg_thread = [
    "---------------------"
    "Doris",
    "08.07 13:00 td: 1234m",
    "Hello World",
    "Boris 2016.08.07 13:02",
    "Hello World!",
    "Bob 2016.08.07 13.05",
    "yo!"
]


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
        self.yubikey = Yubikey(self.yubikey_status, self.yubikey_auth)
        self.yubikey.start()

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

            #self.message.decrypt_msg_thread(self.display.view_msg_friend)

            #Process message.network_plaintexts function here!!
            self.event.wait(5)

    def stop(self):
        self.log.info("Stopping UI Thread.")
        self.yubikey.stop()
        #self.display.stop()
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

    def auth(self):
        self.display.mode = m_AUTH

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
        elif self.display.mode == m_SYSTEM_MENU:
            self.display.row_index -= 1
            if self.display.row_index < 0:
                self.display.row_index = 0


    def key_down(self, channel):
        self.is_idle = False
        ##print "pressed DOWN Key."
        #self.display.key_down()
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
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
        elif self.display.mode == m_SYSTEM_MENU:
            self.display.row_index += 1
            if self.display.row_index >= len(scr.system_menu):
                self.display.row_index = len(scr.system_menu) -1


    def key_left(self, channel):
        self.is_idle = False
        ##print "pressed LEFT Key."
        #self.display.key_left()
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
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
        elif self.display.mode == m_STATUS_LASTSEEN:
            self.display.mode = m_STATUS

    def key_right(self, channel):
        self.is_idle = False
        ##print "pressed RIGHT Key."
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
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
        elif self.display.mode == m_STATUS:
            self.display.mode = m_STATUS_LASTSEEN


    def key_enter(self, channel):
        self.is_idle = False
        #self.btn_count = 0
        ###print "pressed ENTER Key."
        #self.display.key_enter()
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
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
                    #print "Password len:",len(password)
                    #print "Yubikey psw: ", password
                    #print "Crypt psw: ", crypt_pass
                    #print "Sig psw: ", sig_pass
                    if self.crypto.gen_keysets(crypt_pass,sig_pass,self.config.alias):
                        self.yubikey.set_slot1(password)
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
                #print self.message.compose_msg
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
            #self.message.process_group_messages() #called when new msg is processed

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
                #self.display.dialog_next_mode = m_COMPOSE_MENU
                self.display.mode = m_COMPOSE_MENU
            elif self.display.row_index == 1:
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.dialog_next_mode = m_MAIN_MENU
                self.display.mode = m_MSG_VIEWER
            elif self.display.row_index == 2:
                self.display.mode = m_STATUS
                #self.log.debug( "Generating TRAFFIC")
                #for friend in self.message.friends:
                    #self.message.process_composed_msg('Hello DSCv2.', friend)
            elif self.display.row_index == 3:
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.mode = m_SYSTEM_MENU
            elif self.display.row_index == 4:
                self.display.dialog_cmd = cmd_SHUTDOWN
                self.display.dialog_msg = "Shutdown?"
                self.display.dialog_msg2 = "Are you not entertained?"
                self.display.col_index = 0
                self.display.mode = m_DIALOG_YESNO
        elif self.display.mode == m_SYSTEM_MENU:
            self.log.debug( "SystemMenu Selected: " + scr.system_menu[self.display.row_index])
            if self.display.row_index == 0:     #Update Software
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.dialog_cmd = cmd_SOFTWARE_UPDATE
                self.display.dialog_msg = "Perform Software Update?"
                self.display.dialog_msg2 = ""
                self.display.mode = m_DIALOG_YESNO
            elif self.display.row_index == 1:   #Import Public Keys
                self.display.row_index = 0
                self.display.col_index = 0
                #self.display.mode = m_MSG_VIEWER
            elif self.display.row_index == 2:   #Export Public Keys
                self.display.row_index = 0
                self.display.col_index = 0
                #self.display.mode = m_SYSTEM_MENU
            elif self.display.row_index == 3:   #Generate Keys
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.dialog_cmd = cmd_GEN_KEYSET
                self.display.dialog_msg = "Gen new Keyset?"
                self.display.dialog_msg2 = "DATA will be LOST"
                self.display.dialog_next_mode = m_SYSTEM_MENU
                self.display.mode = m_DIALOG_YESNO
            elif self.display.row_index == 4:   #Wipe USB Drive
                self.display.row_index = 0
                self.display.col_index = 0
            elif self.display.row_index == 5:   #Factory Reset
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.dialog_cmd = cmd_FACTORY_RESET
                self.display.dialog_next_mode = m_SYSTEM_MENU
                self.display.dialog_msg = "Perform Factory Reset?"
                self.display.dialog_msg2 = "ALL DATA will be LOST"
                self.display.mode = m_DIALOG_YESNO
        elif self.display.mode == m_DIALOG_YESNO:
            if self.display.col_index == 1:
                if self.display.dialog_cmd == cmd_SHUTDOWN:
                    self.display.dialog_msg = "Shutting down..."
                    self.display.dialog_msg2 = "Have a nice day."
                    self.display.dialog_task_done = False
                    self.display.mode = m_DIALOG_TASK
                    os.system("sudo shutdown -h now")
                elif self.display.dialog_cmd == cmd_GEN_KEYSET:
                    self.display.dialog_msg = "Generating Keyset"
                    self.display.dialog_msg2 = "Please wait..."
                    self.display.dialog_task_done = False
                    self.display.dialog_next_mode = m_SYSTEM_MENU
                    self.display.mode = m_DIALOG_TASK
                    self.event.wait(0.5)
                    password = self.crypto.generate_random_password(38)
                    sig_pass =str(password)[:len(password)/2]
                    crypt_pass = str(password)[len(password)/2:]
                    #print "Password len:",len(password)
                    #print "Yubikey psw: ", password
                    #print "Crypt psw: ", crypt_pass
                    #print "Sig psw: ", sig_pass
                    if self.crypto.gen_keysets(crypt_pass,sig_pass,self.config.alias):
                        self.yubikey.set_slot1(password)
                        self.display.dialog_msg = "Keyset Generated!"
                        self.display.dialog_msg2 = "Test yubikey password"
                        self.display.dialog_msg3 = "==[Press Yubikey]=="
                    else:
                        self.display.dialog_msg = "Err: Gen Keysets"
                        self.display.dialog_msg2 = "Keyset Already Exists"
                        self.display.dialog_msg3 = "==[Press any key]=="
                        self.display.mode = m_DIALOG
                    password = "" # Unneccessary!?
                elif self.display.dialog_cmd == cmd_FACTORY_RESET:
                    self.display.dialog_msg = "Factory Resetting"
                    self.display.dialog_msg2 = "Please wait..."
                    self.display.dialog_task_done = False
                    self.display.dialog_next_mode = m_AUTH
                    self.display.mode = m_DIALOG_TASK
                    self.event.wait(0.5)
                    self.crypto.wipe_all_data(self.config.alias)
                    self.display.dialog_msg = "Factory Reset"
                    self.display.dialog_msg2 = "Complete!"
                    self.display.dialog_msg3 = "==[Press Anykey]=="
                    self.display.mode = m_DIALOG

            else:
                self.display.row_index = 0
                self.display.col_index = 0
                self.display.mode = self.display.dialog_next_mode



    def key_back(self, channel):
        self.is_idle = False
        if self.display.mode == m_IDLE:
            #self.display.mode = m_LOCK
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


    def yubikey_status(self,is_present):
        if is_present:
            self.log.debug("Yubikey Inserted")
            self.auth()
        else:
            #Perform System Wipe (Lock keys, wipe any user data from memory)
            #Clear Friend List
            self.lock()
            self.crypto.keyset_password_crypt = ''
            self.message.auth = False
            self.log.debug("Yubikey Removed")

    def yubikey_auth(self, password):
        #Check password (i.e. attempt to unlock key chain)
        #If pass, then unlock the screen, else show error? or silence??
        if self.display.dialog_cmd == cmd_GEN_KEYSET:
            self.display.dialog_cmd = ""
            sig_pass =str(password)[:len(password)/2]
            crypt_pass =str(password)[len(password)/2:]
            #print "Password len:",len(password)
            #print "Yubikey psw: ", password
            #print "Crypt psw: ", crypt_pass
            #print "Sig psw: ", sig_pass
            if self.crypto.authenticate_user(crypt_pass, sig_pass, self.config.alias):
                self.display.dialog_msg = "Keyset Psw Auth Good!"
                self.display.dialog_msg2 = ""
                self.display.dialog_msg3 = "==[Press any key]=="
            else:
                self.display.dialog_msg = "Keyset Psw Auth Failed"
                self.display.dialog_msg2 = "Factory Reset."
                self.crypto.wipe_all_data(self.config.alias)
                #self.display.dialog_msg3 = "==[Press any key]=="
            self.display.mode = m_DIALOG
        elif self.display.mode == m_AUTH:
            self.log.info("Checking Yubikey Authentication Password. ")
            sig_pass =str(password)[:len(password)/2]
            crypt_pass =str(password)[len(password)/2:]
            #print "Password len:",len(password)
            #print "Yubikey psw: ", password
            #print "Crypt psw: ", crypt_pass
            #print "Sig psw: ", sig_pass
            if self.crypto.authenticate_user(crypt_pass, sig_pass, self.config.alias):
                self.main_menu()
                #self.message.auth = True
                #self.message.sig_auth = True
            else:
                print self.config.alias
                if self.config.alias == "unreg":
                    self.log.info( "Starting Registration Process.")
                    self.config.alias = ""
                    self.display.mode = m_REG
