#!/usr/bin/python
# ---------------------------------------
# --- Dirt Simple Comms GLobals
#----------------------------------------
import ConfigParser
import os
import errno
import logging

CONFIG_PATH = "/dscdata"
CONFIG_FILE = "dsc.config"

class Config(object):
    def __init__(self):
        self.log = logging.getLogger()

        self.hw_rev = 2 
        self.airplane_mode = True
        self.tdma_slot = 0
        self.tdma_total_slots = 2
        self.tx_time = 4
        self.tx_deadband = 1

        self.freq = 0
        self.bandwidth = 0
        self.bandwidth_eng = ''
        self.spread_factor = 0
        self.coding_rate = 0
        self.coding_rate_eng = ''
        self.tx_power = 0
        self.sync_word = 0

        self.cfg = ConfigParser.ConfigParser()
        try:
            os.makedirs(CONFIG_PATH)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
        if os.path.isfile(CONFIG_PATH + '/' + CONFIG_FILE):
            self.load_config()
        else:
            self.save_config(False)


    def update_bandwidth_eng(self): #Units kHz
        if self.bandwidth == 0:
            self.bandwidth_eng = "62.5 kHz"
        elif self.bandwidth == 1:
            self.bandwidth_eng = "125 kHz"
        elif self.bandwidth == 2:
            self.bandwidth_eng = "250 kHz"
        elif self.bandwidth == 3:
            self.bandwidth_eng = "500 kHz"

    def update_coding_rate_eng(self): 
        if self.coding_rate == 1:
            self.coding_rate_eng = "4/5"
        elif self.coding_rate == 2:
            self.coding_rate_eng = "4/6"
        elif self.coding_rate == 3:
            self.coding_rate_eng = "4/7"
        elif self.coding_rate == 4:
            self.coding_rate_eng = "4/8"

    def gen_new(self):
        self.cfg = None
        self.save_config(False)

    def save_config(self,  is_exist):
        with open(CONFIG_PATH + '/' + CONFIG_FILE,'w') as cfgfile:
            if not is_exist:
                print "Generating config file."
                self.cfg.add_section('Network')
            try:
                self.cfg.set('Network','Hardware_Rev',self.hw_rev)
                self.cfg.set('Network','TDMA_Slot',self.tdma_slot)
                self.cfg.set('Network','TDMA_Total_Slots',self.tdma_total_slots)
                self.cfg.set('Network','TX_Time',self.tx_time)
                self.cfg.set('Network','TX_Deadband',self.tx_deadband)
                self.cfg.set('Network','Airplane_Mode',self.airplane_mode)
                self.cfg.write(cfgfile)
            except Exception as e:
                self.log.error(str(e))

    def load_config(self):
        try:
            self.cfg.read(CONFIG_PATH + '/' + CONFIG_FILE)
            self.hw_rev = self.cfg.getint("Network","Hardware_Rev")
            self.tdma_slot = self.cfg.getint("Network","TDMA_Slot")
            self.tdma_total_slots = self.cfg.getint("Network","TDMA_Total_Slots")
            self.tx_time = self.cfg.getint("Network","TX_Time")
            self.tx_deadband = self.cfg.getint("Network","TX_Deadband")
            self.airplane_mode = self.cfg.getboolean("Network","Airplane_Mode")
        except Exception as e:
            self.log.error(str(e))
