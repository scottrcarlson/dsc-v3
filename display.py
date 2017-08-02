#!/usr/bin/python

# --- OLED Display Thread----------------------------
from time import sleep
import RPi.GPIO as GPIO
from oled.device import ssd1306, sh1106
from oled.render import canvas
from PIL import ImageDraw, Image, ImageFont
import iodef
import os
from threading import *
import screen as scr
import time
import logging


#DISPLAY MODES
m_IDLE = 0
m_SETTINGS = 1
m_SPLASH = 2
m_LOG_VIEWER = 3
m_COMPOSE_MENU = 4
m_COMPOSE = 5
m_MAIN_MENU = 6
m_DIALOG = 7
m_MSG_VIEWER = 8
m_DIALOG_YESNO = 9
m_DIALOG_TASK = 11
m_REG = 12
m_STATUS = 13
m_RF_TUNING = 14
m_LOCK=15


keyboard = "abcdefghijklmnopqrstuvwxyz1234567890!?$%.-"

class Display(Thread):
    def __init__(self, message, version, config, radio, sw_rev, heartbeat):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()

        self.heartbeat = heartbeat
        
        if sw_rev == 1:
            self.reset() #Needed for V2

        self.config = config
        self.version = version
        self.sw_rev = sw_rev
        self.message = message
        self.radio = radio

    	# TODO: gracefully handle exception when OLED absent
        if self.config.hw_rev == 1:
            self.device = sh1106(port=1, address=0x3C)
        else:
            #self.device = Adafruit_SSD1306.SSD1306_128_64(rst=24)
            self.device = ssd1306(port=1, address=0x3C)
        self.font = ImageFont.load_default()
        #self.font = ImageFont.truetype("5by7.ttf",10)
        self.mode = m_IDLE

        self.row_index = 0
        self.col_index = 0
        self.char_space = 6
        self.char_size = 4
        self.row_height = 12
        self.screen_row_size = 5
        self.screen_col_size = 21
        self.horiz_min = 0
        self.horiz_max = self.screen_col_size
        self.horiz_index = 0
        self.horiz_reset_cnt = 0
        self.horiz_start_cnt = 0
        self.viz_min = 0
        self.viz_max = self.screen_row_size

        self.dialog_msg = ""
        self.dialog_msg2 = ""
        self.dialog_msg3 = ""
        self.dialog_confirmed = False
        self.dialog_cmd = 0
        self.dialog_task_done = False
        self.dialog_next_mode = m_MAIN_MENU

        self.cursor = True
        self.cursor_x = 0
        self.cursor_y = 0
        self.key_repeating = False

        self.log_tail_results = []

        self.reg_stage = 1   #WNode Registration Stage. 1/Name,2/NetKey,3/GrpKey
        self.log.info("Initialized Display Thread.")

    def log_tail(self,f, n):
        assert n >= 0
        pos, lines = n+1, []
        while len(lines) <= n:
            try:
                f.seek(-pos, 2)
            except IOError:
                f.seek(0)
                break
            finally:
                lines = list(f)
            pos *= 2
        stripped_lines = []

        for line in lines[-n:]:
            split_line = line.split("|")
            stripped_lines.append(split_line[3].strip())
        return stripped_lines

    def run(self):
        self.event.wait(1)
        
        heartbeat_time = 0
        log_time = 0
        while not self.event.is_set():
            try:
                if time.time() - heartbeat_time > 5:
                    heartbeat_time = time.time()
                    if self.heartbeat.qsize() == 0:
                        self.heartbeat.put_nowait("hb")
                elif time.time() - heartbeat_time < 0:
                    self.log.warn("Time changed to past. Re-initializing.")
                    heartbeat_time = time.time()
            except Exception as e:
                self.log.error(str(e))
            #------[IDLE]--------------------------------------------------------------------------
            if self.mode == m_IDLE:
                with canvas(self.device) as draw:
                    #Does this cost energy? Should we only do this first pass?
                    pass
            #------[SPLASH SCREEN]------------------------------------------------------------------$
            elif self.mode == m_SPLASH:
                with canvas(self.device) as draw:
                    logo = Image.open('/home/pi/dsc.png')
                    draw.text((6, 0), 'dirt   simple  comms', font=self.font, fill=255)
                    draw.bitmap((0, 10), logo, fill=1)
            #------[LOCK SCREEN]------------------------------------------------------------------$
            elif self.mode == m_LOCK:
                with canvas(self.device) as draw:
                    logo = Image.open('/home/pi/dsc.png')
                    draw.text((6, 0), 'dirt   simple  comms', font=self.font, fill=255)
                    draw.bitmap((0, 10), logo, fill=1)
                    draw.text((0,40), "LEFT & BACK to Unlock", font=self.font, fill=255)
                    draw.text((0,50), "       New Msgs",font=self.font, fill=255)
            #------[LOG VIEWER]------------------------------------------------------------------$
            elif self.mode == m_LOG_VIEWER:
                try:
                    if time.time() - log_time > 1:
                        with open('/dscdata/dsc.log','r') as logfile:
                            self.log_tail_results = self.log_tail(logfile, 6)
                    log_tail_results = self.log_tail_results
                    with canvas(self.device) as draw:
                        for i in range(0,6):
                            draw.text((0, i*10), log_tail_results[i], font=self.font, fill=255)
                except Exception as e:
                    self.log.error(str(e))
                
            #------[MAIN MENU]----------------------------------------------------------------------
            elif self.mode == m_MAIN_MENU:
                try:
                    with canvas(self.device) as draw:
                        draw.line((121,3,124,0), fill=255)
                        draw.line((124,0,127,3), fill=255)
                        if (self.row_index < self.viz_min):
                            self.viz_max -= self.viz_min - self.row_index
                            self.viz_min = self.row_index
                        elif (self.row_index >= self.viz_max):
                            self.viz_max = self.row_index + 1
                            self.viz_min = self.viz_max - self.screen_row_size
                        #print "Row Index: ", self.row_index, " Viz_Min:", self.viz_min, " Viz_Max:", self.viz_max
                        for i in range(0,len(scr.main_menu)):
                            draw.text((5, 4+( (i-self.viz_min) * self.row_height) ), scr.main_menu[i], font=self.font, fill=255)
                        draw.line((121,60,124,63), fill=255)
                        draw.line((124,63,127,60), fill=255)

                        draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '>', font=self.font, fill=255)
                except Exception as e:
                    self.log.error(str(e))
            #------[SETTINGS SCREEN]------------------------------------------------------------------$     
            elif self.mode == m_SETTINGS:
                try:
                    with canvas(self.device) as draw:
                        draw.text((0, 0), "-- Network Settings --", font=self.font, fill=255)
                        draw.text((0, 10), "Total Nodes:" + str(self.config.tdma_total_slots), font=self.font, fill=255)
                        draw.text((0, 20), "TDMA Slot(0-n):" + str(self.config.tdma_slot), font=self.font, fill=255)
                        draw.text((0, 30), "TX Time(s):" + str(self.config.tx_time), font=self.font, fill=255)
                        draw.text((0, 40), "Deadband(s):" + str(self.config.tx_deadband), font=self.font, fill=255)
                        draw.text((0, 50), "Packet TTL(s):" + str(self.message.packet_ttl), font=self.font, fill=255)
                        if self.row_index == 1:
                            self.cursor_y = 10
                            self.cursor_x = 12 * 6
                        elif self.row_index == 2:
                            self.cursor_y = 20
                            self.cursor_x = 15 * 6
                        elif self.row_index == 3:
                            self.cursor_y = 30
                            self.cursor_x = 11 * 6
                        elif self.row_index == 4:
                            self.cursor_y = 40
                            self.cursor_x = 12 * 6
                        if self.cursor:
                            draw.text((self.cursor_x, self.cursor_y), "_", font=self.font, fill=255)
                        self.cursor = not self.cursor
                except Exception as e:
                    self.log.error(str(e))
             #------[RF TUNING SCREEN]------------------------------------------------------------------$     
            elif self.mode == m_RF_TUNING:
                try:
                    with canvas(self.device) as draw:
                        #draw.text((0, 0), "----- RF Settings -----", font=self.font, fill=255)
                        draw.text((0, 0), "Freq:" + str(self.radio.freq), font=self.font, fill=255)
                        draw.text((0, 10), "Bandwidth:" + str(self.radio.bandwidth), font=self.font, fill=255)
                        draw.text((0, 20), "Spread Factor:" + str(self.radio.spread_factor), font=self.font, fill=255)
                        draw.text((0, 30), "Coding Rate:" + str(self.radio.coding_rate), font=self.font, fill=255)
                        draw.text((0, 40), "TX Power:" + str(self.radio.tx_power), font=self.font, fill=255)
                        if self.row_index == 1:
                            self.cursor_y = 0
                            self.cursor_x = 5 * 6
                        elif self.row_index == 2:
                            self.cursor_y = 10
                            self.cursor_x = 10 * 6
                        elif self.row_index == 3:
                            self.cursor_y = 20
                            self.cursor_x = 13 * 6
                        elif self.row_index == 4:
                            self.cursor_y = 30
                            self.cursor_x = 11 * 6
                        elif self.row_index == 5:
                            self.cursor_y = 40
                            self.cursor_x = 9 * 6
                        if self.cursor:
                            draw.text((self.cursor_x, self.cursor_y), "_", font=self.font, fill=255)
                        self.cursor = not self.cursor
                except Exception as e:
                    self.log.error(str(e))
            #------[STATUS SCREEN]------------------------------------------------------------------$
            elif self.mode == m_STATUS:
                try:
                    with canvas(self.device) as draw:
                        current_datetime = time.strftime("%H:%M:%S")
                        radio_mode = ''
                        if self.message.is_radio_tx:
                            radio_mode = 'TX'
                        else:
                            radio_mode = 'RX'
                        draw.text((0, 0), radio_mode + " / " + current_datetime, font=self.font, fill=255)

                        row = 1
                        for alias in self.message.recvd_beacons:
                            time_sent,rssi,snr = self.message.recvd_beacons[alias]
                            age_sec = time.time() - time_sent
                            time_since = ""
                            if age_sec < 60:
                                time_since = "now"
                            else:
                                time_since = str(int(age_sec / 60)) + "m"
                            draw.text((0, 10 * row), alias +"|"+ time_since +"|"+str(rssi)+"|"+str(snr), font=self.font, fill=255)
                            row += 1
                except Exception as e:
                    self.log.error(str(e))
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
                try:
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
                except Exception as e:
                    self.log.error(str(e))
            #------[MSG THREAD VIEWER]-------
            elif self.mode == m_MSG_VIEWER:
                try:
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
                        group_cleartexts = self.message.group_cleartexts

                        if len(group_cleartexts) == 0:
                            draw.text((6, 4),"No Messages", font=self.font, fill=255)
                        else:
                            if len(group_cleartexts) < self.viz_max:
                                max = len(group_cleartexts)
                            else:
                                max = self.viz_max

                            for i in range(self.viz_min,max):
                                if i == self.row_index:
                                    if len(group_cleartexts[i]) < self.horiz_max:
                                        hmin = self.horiz_min
                                        hmax = len(group_cleartexts[i])
                                    elif len(group_cleartexts[i]) > self.horiz_max + self.horiz_index:
                                        hmin = self.horiz_min + self.horiz_index
                                        hmax = self.horiz_max + self.horiz_index
                                    else:
                                        if self.horiz_reset_cnt == 3:
                                            self.horiz_reset_cnt = 0
                                            self.horiz_start_cnt = 0
                                            self.horiz_index = 0
                                            hmin = self.horiz_min
                                            hmax = self.horiz_max
                                        else:
                                            self.horiz_reset_cnt += 1

                                    draw.text((6, 4+( (i-self.viz_min) * self.row_height) ), group_cleartexts[i][hmin:hmax], font=self.font, fill=255)
                                else:
                                    draw.text((6, 4+( (i-self.viz_min) * self.row_height) ), group_cleartexts[i], font=self.font, fill=255)

                            if self.horiz_start_cnt == 3:
                                self.horiz_index += 1
                            else:
                                self.horiz_start_cnt += 1

                            if len(group_cleartexts[self.row_index]) > self.screen_col_size - 1:
                                draw.text((0, 4 + (self.row_height* (self.row_index - self.viz_min))), '+', font=self.font, fill=255)    
                            else:
                                draw.text((0, 4 + (self.row_height* (self.row_index - self.viz_min))), '>', font=self.font, fill=255)    
                        draw.line((121,60,124,63), fill=255)
                        draw.line((124,63,127,60), fill=255)

                        #draw.text((0, 4 + (12* (self.row_index - self.viz_min))), '|', font=self.font, fill=255)
                except Exception as e:
                    self.log.error(str(e))
          #------[COMPOSE MSG]----------------------------------------------------------------
            elif self.mode == m_COMPOSE:
                try:
                    self.row = 51 + (self.row_index * self.row_height)
                    self.col = self.char_space * self.col_index
                    with canvas(self.device) as draw:
                        msg_line1 = ""
                        msg_line2 = ""
                        msg_line3 = ""
                        if len(self.message.compose_msg) > self.horiz_max:
                            msg_line1 = self.message.compose_msg[:self.horiz_max]
                            if len(self.message.compose_msg) > self.horiz_max * 2:
                                msg_line2 = self.message.compose_msg[self.horiz_max:self.horiz_max*2]
                                msg_line3 = self.message.compose_msg[self.horiz_max*2:]
                            else:
                                msg_line2 = self.message.compose_msg[self.horiz_max:]
                        else:
                            msg_line1 = self.message.compose_msg
                        draw.text((0, 0), msg_line1, font=self.font, fill=255)
                        draw.text((0, 10), msg_line2, font=self.font, fill=255)
                        draw.text((0, 20), msg_line3, font=self.font, fill=255)

                        draw.line((0, 39, 127, 39), fill=255)
                        draw.text((0, 40), keyboard[:21], font=self.font, fill=255)
                        draw.text((0, 52), keyboard[21:], font=self.font, fill=255)
                        if self.row_index >= 0:
                            draw.text((0, 28), ' SND  SPC  CLR  BAIL ', font=self.font, fill=255)
                            if self.key_repeating:
                                self.cursor = True
                            if self.cursor:
                                draw.line((self.col, self.row, self.char_size+self.col, self.row), fill=255)
                            self.cursor = not self.cursor
                        else:
                            if self.col_index == 0:
                                draw.text((0, 28), '<SND> SPC  CLR  BAIL ', font=self.font, fill=255)
                            elif self.col_index == 1:
                                draw.text((0, 28), ' SND <SPC> CLR  BAIL ', font=self.font, fill=255)
                            elif self.col_index == 2:
                                draw.text((0, 28), ' SND  SPC <CLR> BAIL ', font=self.font, fill=255)
                            elif self.col_index == 3:
                                draw.text((0, 28), ' SND  SPC  CLR <BAIL>' , font=self.font, fill=255)
                except Exception as e:
                    self.log.error(str(e))
          #------[DEVICE REGISTRATION]----------------------------------------------------------------------
            elif self.mode == m_REG:
                try:
                    self.row = 51 + (self.row_index * self.row_height)
                    self.col = self.char_space * self.col_index
                    with canvas(self.device) as draw:
                        draw.text((0, 0), "Name:", font=self.font, fill=255)
                        draw.text((0, 8), "NetK:", font=self.font, fill=255)
                        draw.text((0, 16), "GrpK:", font=self.font, fill=255)
                        draw.text((30, 0), self.message.alias, font=self.font, fill=255)
                        draw.text((30, 8), self.message.network_key, font=self.font, fill=255)
                        draw.text((30, 16), self.message.group_key, font=self.font, fill=255)
                        if self.reg_stage == 1:
                            self.cursor_y = 0
                            self.cursor_x = (len(self.message.alias) * 6) + 30
                        elif self.reg_stage == 2:
                            self.cursor_y = 8
                            self.cursor_x = (len(self.message.network_key) * 6) + 30
                        elif self.reg_stage == 3:
                            self.cursor_y = 16
                            self.cursor_x = (len(self.message.group_key) * 6) + 30

                        if self.cursor and self.reg_stage != 4:
                            draw.text((self.cursor_x, self.cursor_y), "<", font=self.font, fill=255)
                        self.cursor = not self.cursor

                        draw.line((0, 39, 127, 39), fill=255)
                        draw.text((0, 40), keyboard[:21], font=self.font, fill=255)
                        draw.text((0, 52), keyboard[21:], font=self.font, fill=255)

                        if self.row_index >= 0:
                            if self.reg_stage == 4:
                                draw.text((20, 28), ' NEXT   DONE ', font=self.font, fill=255)
                            else:
                                draw.text((20, 28), ' NEXT ', font=self.font, fill=255)
                            if self.key_repeating:
                                self.cursor = True
                            if self.cursor:
                                draw.line((self.col, self.row, self.char_size+self.col, self.row), fill=255)
                        else:
                            if self.col_index == 0:
                                if self.reg_stage == 4:
                                    draw.text((20, 28), '<NEXT>  DONE ', font=self.font, fill=255)
                                else:
                                    draw.text((20, 28), '<NEXT>', font=self.font, fill=255)
                            elif self.col_index == 1:
                                if self.reg_stage == 4:
                                    draw.text((20, 28), ' NEXT  <DONE>', font=self.font, fill=255)
                                else:
                                    draw.text((20, 28), ' NEXT ', font=self.font, fill=255)
                except Exception as e:
                    self.log.error(str(e))
            self.event.wait(0.03)

        with canvas(self.device) as draw:
            pass

    def stop(self):
        self.log.info("Stopping OLED Display Thread.")
        self.event.set()

    def reset(self):
        GPIO.output(iodef.PIN_OLED_RESET, False)
        sleep(1)
        GPIO.output(iodef.PIN_OLED_RESET, True)
