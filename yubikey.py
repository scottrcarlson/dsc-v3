#!/usr/bin/python
# ----------------------------
# --- Yubkikey Helper Classes
#----------------------------

#-----[HID Capturing Resources]--------------------
# adapted from https://stackoverflow.com/a/19757397
# and https://superuser.com/questions/562434/how-can-i-read-input-from-the-hosts-keyboard-when-connected-via-ssh
# BLA https://superuser.com/a/872440
# -o-append-cr
#-----[Yubikey Static Password Manipulation]-------
# "Modified Hexadecimal encoding - a.k.a. 'Modhex'"
# ref https://www.yubico.com/wp-content/uploads/2015/11/Yubico_WhitePaper_Static_Password_Function.pdf
# ref https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html

# from https://github.com/stapelberg/pw-to-yubi/blob/master/pw-to-yubi.pl
#--------------------------------------------------
from threading import *
import usb.core
import string
from evdev import InputDevice, categorize, ecodes
import subprocess
import logging

MIT_YUBIKEY_VENDOR_ID = 0x1050
MIT_YUBIKEY_PRODUCT_ID = 0x0010

SCANCODES = {
    0: None, 1: u'ESC', 2: u'1', 3: u'2', 4: u'3', 5: u'4', 6: u'5', 7: u'6', 8: u'7', 9: u'8',
    10: u'9', 11: u'0', 12: u'-', 13: u'=', 14: u'BKSP', 15: u'TAB', 16: u'q', 17: u'w', 18: u'e', 19: u'r',
    20: u't', 21: u'y', 22: u'u', 23: u'i', 24: u'o', 25: u'p', 26: u'[', 27: u']', 28: u'CRLF', 29: u'LCTRL',
    30: u'a', 31: u's', 32: u'd', 33: u'f', 34: u'g', 35: u'h', 36: u'j', 37: u'k', 38: u'l', 39: u';',
    40: u'"', 41: u'`', 42: u'LSHFT', 43: u'\\', 44: u'z', 45: u'x', 46: u'c', 47: u'v', 48: u'b', 49: u'n',
    50: u'm', 51: u',', 52: u'.', 53: u'/', 54: u'RSHFT', 56: u'LALT', 100: u'RALT'
}

CAPSCODES = {
    0: None, 1: u'ESC', 2: u'!', 3: u'@', 4: u'#', 5: u'$', 6: u'%', 7: u'^', 8: u'&', 9: u'*',
    10: u'(', 11: u')', 12: u'_', 13: u'+', 14: u'BKSP', 15: u'TAB', 16: u'Q', 17: u'W', 18: u'E', 19: u'R',
    20: u'T', 21: u'Y', 22: u'U', 23: u'I', 24: u'O', 25: u'P', 26: u'{', 27: u'}', 28: u'CRLF', 29: u'LCTRL',
    30: u'A', 31: u'S', 32: u'D', 33: u'F', 34: u'G', 35: u'H', 36: u'J', 37: u'K', 38: u'L', 39: u':',
    40: u'\'', 41: u'~', 42: u'LSHFT', 43: u'|', 44: u'Z', 45: u'X', 46: u'C', 47: u'V', 48: u'B', 49: u'N',
    50: u'M', 51: u'<', 52: u'>', 53: u'?', 54: u'RSHFT', 56: u'LALT', 100: u'RALT'
}



class Yubikey(Thread):
    def __init__(self,yubikey_status,yubikey_auth):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger(self.__class__.__name__)
        self.yubikey_status = yubikey_status
        self.yubikey_auth = yubikey_auth
        self.key_present = False
        self.yubikey_input = ""
        self.dev = None
        #self.dev.grab()
        self.caps = False

        self.log.info("Initialized Yubikey Thread Thread.")

    def run(self):
        self.event.wait(1)

        while not self.event.is_set():
            #print "Handling Yubikey Stuff"
            #------[Check for Yubikey Presence]-------------
            devs = usb.core.find(find_all=True)
            is_key_present = False
            for dev in devs:
                for cfg in dev:
                    for intf in cfg:
                        if dev.idVendor == MIT_YUBIKEY_VENDOR_ID and dev.idProduct == MIT_YUBIKEY_PRODUCT_ID:
                            is_key_present = True
            if self.key_present ==  False and is_key_present == True:
                #print "Yubikey Inserted."
                self.yubikey_status(True)
                self.event.wait(0.25)
                if self.dev == None:
                    self.dev = InputDevice('/dev/input/event0')
                self.dev.grab()
                self.yubikey_input = ''

            elif self.key_present == True and is_key_present == False:
                #print "Yubikey Removed."
                self.yubikey_status(False)
                self.dev = None

            self.key_present = is_key_present

            #------[Check for Yubikey Input]---------------
            if self.key_present:
                try:
                    input_avail = True
                    while input_avail:
                        event = self.dev.read_one()
                        if (event == None):
                            input_avail = False
                        if event.type == ecodes.EV_KEY:
                            data = categorize(event)
                            if data.scancode == 42:
                                if data.keystate == 1:
                                    self.caps = True
                                if data.keystate == 0:
                                    self.caps = False
                            if data.keystate == 1:  # Down events only
                                if self.caps:
                                    key_lookup = u'{}'.format(CAPSCODES.get(data.scancode)) or u'UNKNOWN:[{}]'.format(data.scancode)  # $
                                else:
                                    key_lookup = u'{}'.format(SCANCODES.get(data.scancode)) or u'UNKNOWN:[{}]'.format(data.scancode)  # $
                                if (data.scancode != 42) and (data.scancode != 28):

                                    self.yubikey_input += key_lookup
                                # Print it all out!
                                if(data.scancode == 28):
                                    self.log.debug("Received Yubikey Input")
                                    #print self.yubikey_input
                                    self.yubikey_auth(self.yubikey_input)
                                    self.yubikey_input = ''
                except:
                    pass
                self.event.wait(0.01)
            else:
                self.event.wait(1)

    def stop(self):
        self.log.info( "Stopping Yubikey Thread.")
        self.event.set()

    def set_slot1(self,private_key_password):
        proc = subprocess.Popen(["perl", "pw-to-yubi.pl", private_key_password], stdout=subprocess.PIPE)
        ykpersonalize_cmd_line = proc.communicate()[0]
        proc = subprocess.Popen(ykpersonalize_cmd_line.split(' '), stdout=subprocess.PIPE)
        ykpersonalize_output = proc.communicate()[0]
        #Grab control over yubikey input again
        self.dev = InputDevice('/dev/input/event0')
        self.dev.grab()

    def set_slot2(self,private_key_password):
        proc = subprocess.Popen(["perl", "pw-to-yubi.pl", private_key_password], stdout=subprocess.PIPE)
        ykpersonalize_cmd_line = proc.communicate()[0]
        proc = subprocess.Popen(ykpersonalize_cmd_line.split(' '), stdout=subprocess.PIPE)
        ykpersonalize_output = proc.communicate()[0]
        #Grab control over yubikey input again
        self.dev = InputDevice('/dev/input/event0')
        self.dev.grab()
