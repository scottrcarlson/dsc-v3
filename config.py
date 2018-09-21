#!/usr/bin/python
# ---------------------------------------
# --- Dirt Simple Comms GLobals
#----------------------------------------
import ConfigParser
import os
import errno
import logging
import uuid

CONFIG_PATH = "/dscdata"
CONFIG_FILE = "dsc.config"
TEST_FILE = "dsc.test"

class Config(object):
    def __init__(self):
        self.log = logging.getLogger()

        #Hardware Revisions:
        #DSCv2 = 1 (Alpha Standalone)
        #DSCv3 = 2 (Beta Standalone)
        #DSCv3 = 3 (Beta Standalone + BLE Outboarding)
        #DSCv4 = 4 (Alpha BLE Outboarding)
        self.hw_rev = 4
        self.req_update_radio = False
        self.req_save_config = False
        self.req_update_network = False
        self.test_mode = False
        self.node_uuid = str(uuid.uuid4())[:8]
        self.alias = ''
        self.netkey = ''
        self.groupkey = ''
        
        self.airplane_mode = True
        self.freq = 0

        self.tdma_slot = 0
        self.tdma_total_slots = 2
        self.tx_time = 4
        self.tx_deadband = 1
        self.bandwidth = 0
        self.spread_factor = 0
        self.coding_rate = 0
        self.tx_power = 0

        self.e_tx_time = 4
        self.e_tx_deadband = 1
        self.e_bandwidth = 0
        self.e_spread_factor = 0
        self.e_coding_rate = 0
        self.e_tx_power = 0
        self.e_ch_seed = ''

        self.bandwidth_eng = ''
        self.coding_rate_eng = ''
        
        self.sync_word = 0
        self.registered = False

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
        self.log.debug("Saving Settings to Disk")
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
                self.cfg.set('Network','Node_UID',self.node_uuid)
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
            self.node_uuid = self.cfg.get("Network","Node_UID")
  
        except Exception as e:
            self.log.error(str(e))


    def load_testconfig(self):
        try:
            self.cfg.read(CONFIG_PATH + '/' + TEST_FILE)
            self.tdma_slot = self.cfg.getint("Network","TDMA_Slot")
            self.tdma_total_slots = self.cfg.getint("Network","TDMA_Total_Slots")
            self.tx_time = self.cfg.getint("Network","TX_Time")
            self.tx_deadband = self.cfg.getint("Network","TX_Deadband")
            self.airplane_mode = self.cfg.getboolean("Network","Airplane_Mode")
            self.netkey = self.cfg.get("Network","netsecret")
            self.groupkey = self.cfg.get("Network","grpsecret")
            self.alias = self.cfg.get("Network","name")
            self.bandwidth = self.cfg.getint("Radio","bw")
            self.coding_rate = self.cfg.getint("Radio","cr")
            self.spread_factor = self.cfg.getint("Radio","sf")
            self.tx_power = self.cfg.getint("Radio","power")
            self.req_update_network = True
            self.registered = True
            self.test_mode = True
        except Exception as e:
            self.log.error(str(e))


    def load_test_params(self):
        if os.path.isfile(CONFIG_PATH + '/' + TEST_FILE):
            self.load_testconfig()
            self.log.debug("++ Loaded Alternate Test Configuration ++")
            return True
        else:
            return False

    def set_hw_rev(self,hw_rev):
        self.hw_rev = hw_rev
        self.req_save_config = True

    def set_airplane_mode(self,airplane_mode):
        self.airplane_mode = airplane_mode
        self.req_save_config = True

    def set_tdma_slot(self,tdma_slot):
        self.tdma_slot = tdma_slot
        self.req_save_config = True
        self.req_update_network = True

    def set_tdma_total_slots(self,tdma_total_slots):
        self.tdma_total_slots = tdma_total_slots
        self.req_save_config = True
        self.req_update_network = True

    def set_tx_time(self,tx_time):
        self.tx_time = tx_time
        self.req_save_config = True
        self.req_update_network = True

    def set_tx_deadband(self,tx_deadband):
        self.tx_deadband = tx_deadband
        self.req_save_config = True
        self.req_update_network = True

    def set_freq(self,freq):
         if self.freq != freq:
            self.freq = freq
            self.req_update_radio = True

    def set_registered(self,registered):
         self.registered = registered

    def set_alias(self,alias):
         self.alias = alias.ljust(8)

    def set_netkey(self,netkey):
         self.netkey = netkey.ljust(16)

    def set_groupkey(self,groupkey):
         self.groupkey = groupkey.ljust(16)

    def set_bandwidth(self,bandwidth):
        if self.bandwidth != bandwidth:
            self.bandwidth = bandwidth
            self.req_update_radio = True
            
    def set_spread_factor(self,spread_factor):
        if self.spread_factor != spread_factor:
            self.spread_factor = spread_factor
            self.req_update_radio = True

    def set_coding_rate(self,coding_rate):
        if self.coding_rate != coding_rate:
            self.coding_rate = coding_rate
            self.req_update_radio = True

    def set_tx_power(self,tx_power):
        if self.tx_power != tx_power:
            self.tx_power = tx_power
            self.req_update_radio = True

    def set_sync_word(self,sync_word):
        if self.sync_word != sync_word:
            self.sync_word = sync_word
            self.req_update_radio = True
