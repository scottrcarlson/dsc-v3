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

    def gen_new(self):
        self.cfg = None
        self.save_config(False)

    def save_config(self,  is_exist):
        with open(CONFIG_PATH + '/' + CONFIG_FILE,'w') as cfgfile:
            if not is_exist:
                print "Generating config file."
                self.cfg.add_section('Network')
                #self.cfg.add_section('RF')
            try:
                if not self.cfg.has_section('Network'):
                    self.cfg.add_section('Network')
                self.cfg.set('Network','Hardware_Rev',self.hw_rev)
                self.cfg.set('Network','TDMA_Slot',self.tdma_slot)
                self.cfg.set('Network','TDMA_Total_Slots',self.tdma_total_slots)
                self.cfg.set('Network','TX_Time',self.tx_time)
                self.cfg.set('Network','TX_Deadband',self.tx_deadband)
                self.cfg.set('Network','Airplane_Mode',self.airplane_mode)
            except Exception as e:
                self.log.error(str(e))

            #try:
            #    if not self.cfg.has_section('RF'):
            #        self.cfg.add_section('RF')
            #    self.cfg.set('RF','Freq',self.freq)
            #    self.cfg.set('RF','Bandwidth',self.bandwidth)
            #    self.cfg.set('RF','Spread_Factor',self.spread_factor)
            #    self.cfg.set('RF','Coding_Rate',self.coding_rate)
            #    self.cfg.set('RF','Tx_Power',self.tx_power)
            #    #self.cfg.set('RF','Sync_Word',self.sync_word)
            #    self.cfg.write(cfgfile)
            #except Exception as e:
            #    self.log.error(str(e))

    def load_config(self):
        try:
            self.cfg.read(CONFIG_PATH + '/' + CONFIG_FILE)
            self.hw_rev = self.cfg.getint("Network","Hardware_Rev")
            self.tdma_slot = self.cfg.getint("Network","TDMA_Slot")
            self.tdma_total_slots = self.cfg.getint("Network","TDMA_Total_Slots")
            self.tx_time = self.cfg.getint("Network","TX_Time")
            self.tx_deadband = self.cfg.getint("Network","TX_Deadband")
            self.airplane_mode = self.cfg.getboolean("Network","Airplane_Mode")

            #self.freq = self.cfg.getint("RF","Freq")
            #self.bandwidth = self.cfg.getint("RF","Bandwidth")
            #self.spread_factor = self.cfg.getint("RF","Spread_Factor")
            #self.coding_rate = self.cfg.getint("RF","Coding_Rate")
            #self.tx_power = self.cfg.getint("RF","Tx_Power")
            #self.sync_word = self.cfg.getstring("RF","Sync_Word")
        except Exception as e:
            self.log.error(str(e))
