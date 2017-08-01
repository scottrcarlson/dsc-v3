#!/usr/bin/python
# ---------------------------------------
# --- Dirt Simple Comms GLobals
#----------------------------------------
import ConfigParser
import os
import errno

CONFIG_PATH = "/dscdata"
CONFIG_FILE = "dsc.config"

class Config(object):
    def __init__(self):
        self.tdma_slot = 0
        self.tdma_total_slots = 2
        self.tx_time = 4
        self.tx_deadband = 1
        self.hw_rev = 1
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

    def gen_new(self):
        self.cfg = None
        self.save_config(False)

    def save_config(self,  is_exist):
        with open(CONFIG_PATH + '/' + CONFIG_FILE,'w') as cfgfile:
            if not is_exist:
                print "Generating config file."
                self.cfg.add_section('Network')
            self.cfg.set('Network','Hardware_Rev',self.hw_rev)
            self.cfg.set('Network','TDMA_Slot',self.tdma_slot)
            self.cfg.set('Network','TDMA_Total_Slots',self.tdma_total_slots)
            self.cfg.set('Network','TX_Time',self.tx_time)
            self.cfg.set('Network','TX_Deadband',self.tx_deadband)
            self.cfg.write(cfgfile)

    def load_config(self):
        self.cfg.read(CONFIG_PATH + '/' + CONFIG_FILE)
        self.hw_rev = self.cfg.getint("Network","Hardware_Rev")
        self.tdma_slot = self.cfg.getint("Network","TDMA_Slot")
        self.tdma_total_slots = self.cfg.getint("Network","TDMA_Total_Slots")
        self.tx_time = self.cfg.getint("Network","TX_Time")
        self.tx_deadband = self.cfg.getint("Network","TX_Deadband")
