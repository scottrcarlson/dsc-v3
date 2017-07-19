#!/usr/bin/python
# ----------------------------
# --- OLED Display Thread----------------------------
from oled.device import ssd1306, sh1106
from oled.render import canvas
from PIL import ImageDraw, Image, ImageFont
from time import sleep
import RPi.GPIO as GPIO
import iodef
import os
from threading import *
import screen as scr
import time
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

keyboard = "abcdefghijklmnopqrstuvwxyz1234567890!?$%.-"

class Display(Thread):
    def __init__(self, message, version, config):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger(self.__class__.__name__)
        self.reset()
        self.config = config
        self.version = version
    	# TODO: gracefully handle exception when OLED absent
        self.device = sh1106(port=1, address=0x3C)
        self.font = ImageFont.load_default()
        #self.font = ImageFont.truetype('./C&C Red Alert [INET].ttf', 12)#mageFont.load_default()
        #self.font_txt = ImageFont.truetype('./C&C Red Alert [INET].ttf', 12)
        self.mode = m_IDLE

        self.row_index = 0
        self.col_index = 0
        self.char_space = 6
        self.char_size = 4
        self.row_height = 12
        self.screen_row_size = 5
        self.viz_min = 0
        self.viz_max = self.screen_row_size



        self.message = message

        #Show a Msg for x amount of seconds
        self.dialog_msg = ""
        self.dialog_msg2 = ""
        self.dialog_msg3 = ""
        self.dialog_confirmed = False
        self.dialog_cmd = 0
        self.dialog_task_done = False
        self.dialog_next_mode = m_MAIN_MENU
        self.log.info("Initialized Display Thread.")

    def run(self):
        self.event.wait(1)
        while not self.event.is_set():
            #------[IDLE]--------------------------------------------------------------------------
            if self.mode == m_IDLE:
                with canvas(self.device) as draw:
                    pass
            #------[LOCK SCREEN]------------------------------------------------------------------$
            elif self.mode == m_LOCK:
                with canvas(self.device) as draw:
                    logo = Image.open('/home/pi/dsc.png')
                    draw.bitmap((0, 20), logo, fill=1)
                    #draw.text((105, 52), 'SYNC', font=self.font, fill=255)
                    current_datetime = time.strftime("%H:%M:%S")
                    draw.text((6, 0), current_datetime, font=self.font, fill=255)
                    draw.text((6, 10), 'dirt   simple  comms', font=self.font, fill=255)
                    draw.text((0, 52), self.version, font=self.font, fill=255)
                    draw.text((45, 52), 'insert key', font=self.font, fill=255)
            #------[AUTH SCREEN]------------------------------------------------------------------$
            elif self.mode == m_AUTH:
                with canvas(self.device) as draw:
                    logo = Image.open('/home/pi/dsc.png')
                    draw.text((6, 0), 'dirt   simple  comms', font=self.font, fill=255)
                    draw.bitmap((0, 10), logo, fill=1)
                    #draw.text((105, 52), 'SYNC', font=self.font, fill=255)
                    current_datetime = time.strftime("%H:%M:%S")
                    #draw.text((6, 0), current_datetime, font=self.font, fill=255)


                    #draw.text((0, 52), self.version, font=self.font, fill=255)
                    draw.text((54, 40), 'psw?', font=self.font, fill=255)
                    draw.text((60, 52), '      equal', font=self.font, fill=255)

            #------[STATUS SCREEN]------------------------------------------------------------------$
            elif self.mode == m_STATUS:
                with canvas(self.device) as draw:
                    logo = Image.open('/home/pi/dsc.png')
                    draw.bitmap((0, 0), logo, fill=1)
                    #draw.text((105, 52), 'SYNC', font=self.font, fill=255)
                    current_datetime = time.strftime("%H:%M:%S")
                    draw.text((0, 30), current_datetime, font=self.font, fill=255)
                    #draw.text((0, 52), self.version, font=self.font, fill=255)

                    #if self.message.stats_max_repeat_size != 0:
                    #    progress_bar = (len(self.message.repeat_msg_list) / float(self.message.stats_max_repeat_size)) * 127
                    #else:
                    progress_bar = 0

                    draw.rectangle((0, 42, 127, 49), outline=255, fill=0)
                    draw.rectangle((0, 42, int(progress_bar), 49), fill=255)
                    #draw.text((0, 52), '%d/%d'%(len(self.message.repeat_msg_list),self.message.stats_max_repeat_size), font=self.font, fill=255)

                    radio_mode = ''
                    if self.message.is_radio_tx:
                        radio_mode = 'TX'
                    else:
                        radio_mode = 'RX'

                    #if self.message.quiet_mode:
                    #    draw.text((35, 52), ' [' + radio_mode + '] net quiet', font=self.font, fill=255)
                    #elif self.message.network_equal:
                    #    draw.text((35, 52), '    [' + radio_mode + '] net eq', font=self.font, fill=255)
                    #else:
                    #    draw.text((35, 52), '[' + radio_mode + '] net not eq', font=self.font, fill=255)
                    #draw.text((0, 55), '[0] msgs unread', font=self.font, fill=255)
            #------[STATUS SCREEN]------------------------------------------------------------------$
            elif self.mode == m_STATUS_LASTSEEN:
                    with canvas(self.device) as draw:
                        logo = Image.open('/home/pi/dsc.png')
                        draw.bitmap((0, 0), logo, fill=1)
                        draw.text((0, 30), 'Beacon Recvd: ' + self.message.lastseen_name, font=self.font, fill=255)
                        draw.text((0, 40), 'RSSI/SNR: [' + str(self.message.lastseen_rssi) +'][' + str(self.message.lastseen_snr) + ']', font=self.font, fill=255)
                        if self.message.lastseen_time == 0:
                            draw.text((0, 50), 'Never seen.', font=self.font, fill=255)
                        else:
                            draw.text((0, 50), str( round((time.time() - self.message.lastseen_time) / 60.0,1) ) + ' minutes ago', font=self.font, fill=255)

        #draw.text((0, 55), '[0] msgs unread', font=self.font, fill=255)
            #------[DIALOG]-------------------------------------------------------------------    $
            elif self.mode == m_DIALOG:
                if self.dialog_confirmed:
                    self.dialog_confirmed = False
                    self.dialog_msg = ""
                    self.dialog_msg2 = ""
                    self.dialog_msg3 = ""
                    self.mode = self.dialog_next_mode
                with canvas(self.device) as draw:
                    draw.text((0, 0), self.dialog_msg, font=self.font, fill=255)
                    draw.text((0, 10), self.dialog_msg2, font=self.font, fill=255)
                    draw.text((0, 20), self.dialog_msg3, font=self.font, fill=255)
            #------[DIALOG TASK]------------------------------------------------------------------$
            elif self.mode == m_DIALOG_TASK:
                if self.dialog_task_done:
                    self.dialog_task_done = False
                    self.dialog_msg = ""
                    self.dialog_msg2 = ""
                    self.dialog_msg3 = ""
                    self.mode = self.dialog_next_mode
                with canvas(self.device) as draw:
                    draw.text((0, 0), self.dialog_msg, font=self.font, fill=255)
                    draw.text((0, 10), self.dialog_msg2, font=self.font, fill=255)
                    draw.text((0, 20), self.dialog_msg3, font=self.font, fill=255)

            #------[DIALOG YESNO]-----------------------------------------------------------------$
            elif self.mode == m_DIALOG_YESNO:
                with canvas(self.device) as draw:
                    draw.text((0, 0), self.dialog_msg, font=self.font, fill=255)
                    draw.text((0, 10), self.dialog_msg2, font=self.font, fill=255)
                    draw.text((0, 20), self.dialog_msg3, font=self.font, fill=255)
                    if self.col_index == 0:
                        draw.text((30, 40), '<NO>     YES ', font=self.font, fill=255)
                    elif self.col_index == 1:
                        draw.text((30, 40), ' NO     <YES> ', font=self.font, fill=255)

           #------[MSG COMPOSE MENU]-------
            elif self.mode == m_COMPOSE_MENU:
                with canvas(self.device) as draw:
                    draw.line((121,3,124,0), fill=255)
                    draw.line((124,0,127,3), fill=255)
                    if (self.row_index < self.viz_min):
                        self.viz_max -= self.viz_min - self.row_index
                        self.viz_min = self.row_index
                    if (self.row_index >= self.viz_max):
                        self.viz_max = self.row_index + 1
                        self.viz_min = self.viz_max - self.screen_row_size
                    #print "Row Index: ", self.row_index, " Viz_Min:", self.viz_min, " Viz_Max:", self.viz_max
                    if len(scr.compose_menu) < self.viz_max:
                        max = len(scr.compose_menu)
                    else:
                        max = self.viz_max

                    for i in range(self.viz_min,max):
                        draw.text((5, 4+( (i-self.viz_min) * self.row_height) ), scr.compose_menu[i], font=self.font, fill=255)
                    draw.line((121,60,124,63), fill=255)
                    draw.line((124,63,127,60), fill=255)

                    draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '|', font=self.font, fill=255)

            #------[SYSTEM MENU]-------
            elif self.mode == m_SYSTEM_MENU:
                with canvas(self.device) as draw:
                    draw.line((121,3,124,0), fill=255)
                    draw.line((124,0,127,3), fill=255)
                    if (self.row_index < self.viz_min):
                        self.viz_max -= self.viz_min - self.row_index
                        self.viz_min = self.row_index
                    if (self.row_index >= self.viz_max):
                        self.viz_max = self.row_index + 1
                        self.viz_min = self.viz_max - self.screen_row_size
                    #print "Row Index: ", self.row_index, " Viz_Min:", self.viz_min, " Viz_Max:", self.viz_max
                    if len(scr.system_menu) < self.viz_max:
                        max = len(scr.system_menu)
                    else:
                        max = self.viz_max

                    for i in range(self.viz_min,max):
                        draw.text((5, 4+( (i-self.viz_min) * self.row_height) ), scr.system_menu[i], font=self.font, fill=255)
                    draw.line((121,60,124,63), fill=255)
                    draw.line((124,63,127,60), fill=255)

                    draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '|', font=self.font, fill=255)

            #------[MSG THREAD VIEWER]-------
            elif self.mode == m_MSG_VIEWER:
                with canvas(self.device) as draw:
                    draw.line((121,3,124,0), fill=255)
                    draw.line((124,0,127,3), fill=255)
                    if (self.row_index < self.viz_min):
                        self.viz_max -= self.viz_min - self.row_index
                        self.viz_min = self.row_index
                    if (self.row_index >= self.viz_max):
                        self.viz_max = self.row_index + 1
                        self.viz_min = self.viz_max - self.screen_row_size
                    #print "Row Index: ", self.row_index, " Viz_Min:", self.viz_min, " Viz_Max:", self.viz_max

                    if len(self.message.group_cleartexts) < self.viz_max:
                        max = len(self.message.group_cleartexts)
                    else:
                        max = self.viz_max
                    for i in range(self.viz_min,max):
                        draw.text((0, 4+( (i-self.viz_min) * self.row_height) ), self.message.group_cleartexts[i], font=self.font, fill=255)
                    #else:
                        #draw.text((0, 0),"No Messages", font=self.font, fill=255)

                    draw.line((121,60,124,63), fill=255)
                    draw.line((124,63,127,60), fill=255)

                    #draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '|', font=self.font, fill=255)

          #------[COMPOSE MSG]----------------------------------------------------------------
            elif self.mode == m_COMPOSE:
                self.row = 51 + (self.row_index * self.row_height)
                self.col = self.char_space * self.col_index
                with canvas(self.device) as draw:
                    draw.text((0, 0), self.message.compose_msg, font=self.font, fill=255)
                    draw.line((0, 39, 127, 39), fill=255)
                    draw.text((0, 40), keyboard[:21], font=self.font, fill=255)
                    draw.text((0, 52), keyboard[21:], font=self.font, fill=255)
                    if self.row_index >= 0:
                        draw.text((0, 28), ' SND  SPC  CLR  BAIL ', font=self.font, fill=255)
                        draw.line((self.col, self.row, self.char_size+self.col, self.row), fill=255)
                    else:
                        if self.col_index == 0:
                            draw.text((0, 28), '<SND> SPC  CLR  BAIL ', font=self.font, fill=255)
                        elif self.col_index == 1:
                            draw.text((0, 28), ' SND <SPC> CLR  BAIL ', font=self.font, fill=255)
                        elif self.col_index == 2:
                            draw.text((0, 28), ' SND  SPC <CLR> BAIL ', font=self.font, fill=255)
                        elif self.col_index == 3:
                            draw.text((0, 28), ' SND  SPC  CLR <BAIL>' , font=self.font, fill=255)
          #------[DEVICE REGISTRATION]----------------------------------------------------------------------
            elif self.mode == m_REG:
                self.row = 51 + (self.row_index * self.row_height)
                self.col = self.char_space * self.col_index
                with canvas(self.device) as draw:
                    draw.text((0, 0), self.config.alias, font=self.font, fill=255)
                    draw.line((0, 39, 127, 39), fill=255)
                    draw.text((0, 40), keyboard[:21], font=self.font, fill=255)
                    draw.text((0, 52), keyboard[21:], font=self.font, fill=255)
                    if self.row_index >= 0:
                        draw.text((0, 28), ' DONE ', font=self.font, fill=255)
                        draw.line((self.col, self.row, self.char_size+self.col, self.row), fill=255)
                    else:
                        if self.col_index == 0:
                            draw.text((0, 28), '<DONE>', font=self.font, fill=255)

          #------[MAIN MENU]----------------------------------------------------------------------
            elif self.mode == m_MAIN_MENU:
                with canvas(self.device) as draw:
                    draw.line((121,3,124,0), fill=255)
                    draw.line((124,0,127,3), fill=255)
                    if (self.row_index < self.viz_min):
                        self.viz_max -= self.viz_min - self.row_index
                        self.viz_min = self.row_index
                    if (self.row_index >= self.viz_max):
                        self.viz_max = self.row_index + 1
                        self.viz_min = self.viz_max - self.screen_row_size
                    #print "Row Index: ", self.row_index, " Viz_Min:", self.viz_min, " Viz_Max:", self.viz_max
                    for i in range(self.viz_min,self.viz_max):
                        draw.text((5, 4+( (i-self.viz_min) * self.row_height) ), scr.main_menu[i], font=self.font, fill=255)
                    draw.line((121,60,124,63), fill=255)
                    draw.line((124,63,127,60), fill=255)

                    draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '|', font=self.font, fill=255)
            self.event.wait(0.04)

        with canvas(self.device) as draw:
            pass

    def stop(self):
        self.log.info("Stopping OLED Display Thread.")
        self.event.set()

    def reset(self):
        GPIO.output(iodef.PIN_OLED_RESET, False)
        sleep(1)
        GPIO.output(iodef.PIN_OLED_RESET, True)
