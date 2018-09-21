#!/usr/bin/env python

from ll_ifc import ModuleConnection, OPCODES
import sys, time, binascii, struct, os
import RPi.GPIO as GPIO
import datetime
from threading import *
import iodef
import time
import Queue
import logging
import random

#Traceback (most recent call last):
#  File "/home/dsc/dsc/radio.py", line 145, in run
#    False)
#  File "/home/dsc/dsc/radio.py", line 196, in set_params
#    self.mc._send_command(OPCODES['TX_POWER'],bytearray([tx_power]))
#  File "/home/dsc/dsc/ll_ifc.py", line 164, in _send_command
#    response = self._receive_packet(opcode, self.message_counter)
#  File "/home/dsc/dsc/ll_ifc.py", line 223, in _receive_packet
#    Received %s not %s" % (resp_opcode, opcode))
#IOError: Did not get the same opcode we sent:                Received 15 not 7
#2018-09-05 12:52:37,277| radio       | ERROR   | Radio Run Task Error: Did not get the same opcode we sent:                Received 15 not 7
class Radio(Thread):
    def __init__(self,serial_device, config, message, heartbeat):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()

        self.heartbeat = heartbeat
        #self.log.setLevel(logging.DEBUG)

        self.serial_device = serial_device
        self.config = config
        self.message = message

        self.ignore_radio_irq = False
        self.radio_verbose = 0

        self.total_recv = 0
        self.total_sent = 0
        self.total_exceptions = 0

        #Edge Detection
        self.prev_total_sent = 0
        self.prev_total_recv = 0
        self.prev_total_exceptions = 0
        self.prev_private_mode_send_flag = self.message.private_mode_send_flag
        self.prev_private_mode = self.message.private_mode
        self.is_radio_tx = False

        self.last_tx = 0
        self.tx_throttle = 0.5 # Should we calculate based on rf parameters and packet size? YES
        self.frame_config_width = 2 # n seconds at the beginning of frame to allow for configuration changes
        self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
        self.tdma_frame_width = (self.tdma_slot_width * self.config.tdma_total_slots) + self.frame_config_width

        self.vchannel_freq = 0

        self.is_check_outbound = False
        self.is_check_inbound = True
        self.update_stats = True


        self.mc = ModuleConnection(self.serial_device)

        self.reset_radio()
        GPIO.add_event_detect(iodef.PIN_RADIO_IRQ, GPIO.RISING, callback=self.check_irq, bouncetime=100)

        self.log.info('Initialized Radio Thread.')
        self.log.debug("Antenna Active:" + self.mc.get_antenna())
        self.config.freq, self.config.bandwidth, self.config.spread_factor, self.config.coding_rate, self.config.tx_power, self.config.sync_word = self.get_params()
        if self.config.load_test_params():
            self.set_params(self.config.freq, 
                                        self.config.bandwidth, 
                                        self.config.spread_factor, 
                                        self.config.coding_rate, 
                                        self.config.tx_power, 
                                        self.config.sync_word,
                                        False)

        self.log.debug("Freq:" + str(self.config.freq) + " hz")
        self.log.debug("TX Power: " + str(self.config.tx_power) + " dBm")
        self.log.debug("Bandwidth:" + str(self.config.bandwidth))
        self.log.debug("SpreadFactor:" + str(self.config.spread_factor))
        self.log.debug("Coding Rate:" + str(self.config.coding_rate))
        self.log.debug("Sync Word:" + str(self.config.sync_word))

        self.config.update_bandwidth_eng()
        self.config.update_coding_rate_eng()

        self.ble_handset_rf_status_queue = Queue.Queue()
        self.radio_version = self.mc.get_version()
        self.log.debug("Firmware Version: " + str(self.radio_version))
        self.txing = False
    def run(self):
        self.event.wait(1)
        last_checked_tdma = 0
        heartbeat_time = 0
        prev_epoch_tdma_frames = 0
        chkcfg_time = 0
        while not self.event.is_set():
            try:
                if time.time() - heartbeat_time > 5:
                    heartbeat_time = time.time()
                    if self.heartbeat.qsize() == 0:
                        self.heartbeat.put_nowait("hb")
                elif time.time() - heartbeat_time < 0:
                    self.log.warn("Time changed to past. Re-initializing.")
                    heartbeat_time = time.time()

                if time.time() - chkcfg_time > 1:
                    chkcfg_time = time.time()
                    if self.config.req_update_network:
                        self.config.req_update_network = False
                        self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
                        self.tdma_frame_width = (self.tdma_slot_width * self.config.tdma_total_slots) + self.frame_config_width
                        self.log.debug("Network Configuration Updated")
                    if self.config.req_update_radio:
                        self.config.req_update_radio = False
                        self.set_params(self.config.freq, 
                                        self.config.bandwidth, 
                                        self.config.spread_factor, 
                                        self.config.coding_rate, 
                                        self.config.tx_power, 
                                        self.config.sync_word,
                                        True)
                        self.log.debug("Radio Settings Updated")
            except Exception as e:
                self.log.error(str(e))
            self.event.wait(0.05)

            try:
                if self.config.registered:
                    if self.is_check_inbound and not self.is_radio_tx:
                        self.process_inbound_msg()
                    elif self.is_radio_tx and (time.time() - self.last_tx) > self.tx_throttle:
                        self.last_tx = time.time()
                        self.process_outbound_msg()
                    if time.time() - self.last_tx < 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        self.last_tx = time.time()

                    #if self.total_sent != self.prev_total_sent or self.total_recv != self.prev_total_recv or self.total_exceptions != self.prev_total_exceptions:
                    #    self.prev_total_sent = self.total_sent
                    #    self.prev_total_recv = self.total_recv
                    #    self.prev_total_exceptions = self.total_exceptions
                        #print "== Sent: [",self.total_sent,"]  Recvd:[",self.total_recv,"] Radio Exceptions:[",self.total_exceptions,"] =="

                    if (time.time() - last_checked_tdma) > 0.1: #Check to see if our TDMA Slot is Active
                        last_checked_tdma = time.time()
                        epoch = last_checked_tdma
                        epoch_tdma_frames = int(epoch / self.tdma_frame_width)

                        slot_start = self.frame_config_width + (self.config.tdma_slot * self.tdma_slot_width) + (self.tdma_frame_width * epoch_tdma_frames)
                        slot_end = slot_start + self.tdma_slot_width
                        #print self.tdma_frame_width
                       
                        if (epoch_tdma_frames != prev_epoch_tdma_frames):
                            prev_epoch_tdma_frames = epoch_tdma_frames

                            #New TDMA Frame, check and set network configuration
                            if self.message.private_mode != self.message.PRIVATE_MODE_DISABLED:
                                random.seed(self.config.netkey + self.config.e_ch_seed + str(epoch_tdma_frames))
                                self.vchannel_freq = int(str(int(random.uniform(90250000,92750000))).ljust(9, '0'))
                                self.log.debug("Private Virtual Channel Freq: " + str(self.vchannel_freq))
                                self.set_params(self.vchannel_freq, 
                                            self.config.e_bandwidth, 
                                            self.config.e_spread_factor, 
                                            self.config.e_coding_rate, 
                                            self.config.e_tx_power, 
                                            self.config.sync_word,
                                            False)
                                if not self.is_radio_tx:
                                    self.set_radio_recv_mode()

                            else:
                                random.seed(self.config.netkey + str(epoch_tdma_frames))
                                self.vchannel_freq = int(str(int(random.uniform(90250000,92750000))).ljust(9, '0'))
                                self.log.debug("Main Virtual Channel Freq: " + str(self.vchannel_freq))
                                self.set_params(self.vchannel_freq, 
                                            self.config.bandwidth, 
                                            self.config.spread_factor, 
                                            self.config.coding_rate, 
                                            self.config.tx_power, 
                                            self.config.sync_word,
                                            False)

                        if self.message.private_mode == self.message.PRIVATE_MODE_PRIMARY:
                            if self.message.private_mode != self.prev_private_mode:
                                self.prev_private_mode = self.message.private_mode
                                self.prev_private_mode_send_flag = self.message.private_mode_send_flag
                                self.log.debug("[TX mode] Transmitting Data")
                                self.is_radio_tx = True
                            elif self.message.private_mode_send_flag != self.prev_private_mode_send_flag:
                                self.prev_private_mode_send_flag = self.message.private_mode_send_flag
                                if self.message.private_mode_send_flag:
                                    self.log.debug("[TX mode] Transmitting Data")
                                    self.is_radio_tx = True
                                else:
                                    self.log.debug("[RX mode] Listening for Ack")
                                    self.is_radio_tx = False
                                    self.set_radio_recv_mode()
                        elif self.message.private_mode == self.message.PRIVATE_MODE_SECONDARY:
                            if self.message.private_mode != self.prev_private_mode:
                                self.prev_private_mode = self.message.private_mode
                                self.prev_private_mode_send_flag = self.message.private_mode_send_flag
                                self.is_radio_tx = False
                                self.log.debug("[RX mode] Listening for Data")
                                self.set_radio_recv_mode()
                            elif self.message.private_mode_send_flag != self.prev_private_mode_send_flag:
                                self.prev_private_mode_send_flag = self.message.private_mode_send_flag
                                if self.message.private_mode_send_flag:
                                    self.log.debug("[TX mode] Sending Ack")
                                    self.is_radio_tx = True
                                    self.event.wait(2) #hack
                                else:
                                    self.is_radio_tx = False
                                    self.log.debug("[RX mode] Listening for Data")
                                    self.set_radio_recv_mode()

                        elif self.message.private_mode == self.message.PRIVATE_MODE_DISABLED:
                            if self.message.private_mode != self.prev_private_mode:
                                self.prev_private_mode = self.message.private_mode
                            if epoch > slot_start and epoch < (slot_end - self.config.tx_deadband):                           
                                if not self.is_radio_tx:
                                    self.is_radio_tx = True
                                    self.message.generate_beacon()
                                    self.log.debug("[TX mode] Transmitting")
                                
                                self.ble_handset_rf_status_queue.queue.clear()
                                self.ble_handset_rf_status_queue.put_nowait([self.config.freq, True])
                            else:
                                if self.is_radio_tx:
                                    self.is_radio_tx = False
                                    self.log.debug("[RX mode] Listening")
                                    self.set_radio_recv_mode()
                                
                                self.ble_handset_rf_status_queue.queue.clear()
                                self.ble_handset_rf_status_queue.put_nowait([self.config.freq, False])

                    elif time.time() - last_checked_tdma < 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        last_checked_tdma = time.time()
            except Exception as e:
                self.log.error(e, exc_info=True)   
                self.log.error("Radio Run Task Error: " + str(e))

    def stop(self):
        self.log.debug("Stopping Radio Thread.")
        self.event.set()

    def set_params(self,freq,bandwidth,spread_factor,coding_rate,tx_power,sync_word,enable_store):
        flags = 255
        parm1 = 0
        parm1 |= ((spread_factor - 6) & 0x07) << 4
        parm1 |= ((coding_rate - 1) & 0x03) << 2
        parm1 |= bandwidth & 0x03
        parm2 = 0b11 # Header Enabled / CRC Enabled / IRQ not Inverted
        preamble_syms = 6
        parm3 = (preamble_syms >> 8) & 0xFF
        parm4 = (preamble_syms >> 0) & 0xFF
        parm5 = (freq >> 24) & 0xFF
        parm6 = (freq >> 16) & 0xFF
        parm7 = (freq >> 8) & 0xFF
        parm8 = freq & 0xFF

        params = bytearray([flags,parm1,parm2,parm3,parm4,parm5,parm6,parm7,parm8])
        self.mc._send_command(OPCODES['SET_RADIO_PARAMS'], params)
        self.mc._send_command(OPCODES['TX_POWER'],bytearray([tx_power]))
        self.mc._send_command(OPCODES['SYNC_WORD_SET'],bytearray([sync_word]))
        
        if enable_store:
            self.mc._send_command(OPCODES['STORE_SETTINGS'])

    def get_params(self):
        params = self.mc._send_command(OPCODES['GET_RADIO_PARAMS'])
        spread_factor = (params[0] >> 4) + 6
        coding_rate = ((params[0] >> 2) & 0x03) + 1
        bandwidth = params[0] & 0x03
        freq = (params[4] << 24)
        freq |= (params[5] << 16)
        freq |= (params[6] << 8)
        freq |= (params[7])
        header_enabled = (params[1] & 0b001 == 1)
        crc_enabled = (params[1] & 0b010 == 2)
        iq_inverted = (params[1] & 0b100 == 4) # 1U << 2U
        preamble_syms = ((params[2] << 8) | params[3])
        tx_power = self.mc._send_command(OPCODES['TX_POWER_GET'])[0]
        sync_word = self.mc._send_command(OPCODES['SYNC_WORD_GET'])[0]
        return freq, bandwidth, spread_factor, coding_rate, tx_power, sync_word

    def signal_quality(self,rssi):
        #Look at these ratings, are they reasonable?
        if rssi > -60:
                quality = "GOOD"
        elif rssi > -75:
                quality = "OK"
        elif rssi > -95:
                quality = "POOR"
        else:
                quality = "BAD"
        return quality

    def process_inbound_msg(self):
        global total_recv
        global total_exceptions
        global is_check_inbound
        try:
            received_data = self.mc._send_command(OPCODES['PKT_RECV_CONT'])
            #sleep(0.01)
            self.event.wait(0.02)
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION PKT_RECV_CONT: ", exc_info=True)

        else:
            if not self.config.airplane_mode:
                if len(received_data) > 0:
                    #GPIO.output(iodef.PIN_LED_RED, True)
                    print "@@@@@@@@@@@@@@@"
                    iodef.PWM_LED_RED.ChangeDutyCycle(5)
                    self.update_stats = True
                    msg = received_data[3:]
                    self.total_recv += 1

                    (rssi, ) = struct.unpack_from('<h', bytes(received_data[:2]))
                    snr = received_data[2] / 4.0

                    if self.config.registered:
                        self.message.radio_inbound_queue.put_nowait((rssi,snr,msg))
                    self.event.wait(0.15)
                    #GPIO.output(iodef.PIN_LED_RED, False)
                    iodef.PWM_LED_RED.ChangeDutyCycle(0)
        finally:
            self.is_check_inbound = False

            try:
                self.mc.clear_irq_flags()
                self.event.wait(0.05)

            except Exception, e:
                if self.radio_verbose > 0:
                    self.log.error( "EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)

    def process_outbound_msg(self):
        if not self.config.airplane_mode:
            outbound_data = ''
            isbeacon = False
            try:
                outbound_data = self.message.radio_beacon_queue.get_nowait()
                #self.log.debug("Sending Beacon: " + str(self.message.radio_beacon_queue.qsize()))
                isbeacon = True
            except Queue.Empty:
                try:
                    outbound_data = self.message.radio_outbound_queue.get_nowait()
                    print "********************** msg queued for tx"
                    #self.tx_throttle = 0.5#((1.0 / 510.0) * len(outbound_data)) + 0.3 #Scale found empiracaly (ie. no radio errors)
                    #self.log.debug(str(len(outbound_data)) + " bytes/tx_throttle=" + str(self.tx_throttle))
                except Queue.Empty:
                    pass
            if outbound_data != '':
                if isbeacon:
                    iodef.PWM_LED_BLUE.ChangeDutyCycle(5)
                    #GPIO.output(iodef.PIN_LED_BLUE, True)
                else:
                    iodef.PWM_LED_GREEN.ChangeDutyCycle(5)
                    #GPIO.output(iodef.PIN_LED_GREEN, True)

                self.is_check_outbound = True
                self.txing = True
                try:
                    r = self.mc._send_command(OPCODES['PKT_SEND_QUEUE'], outbound_data)
                    self.event.wait(0.025)
                    self.is_check_outbound = False

                except Exception, e:
                    if self.radio_verbose > 0:
                        self.log.error("EXCEPTION PKT_SEND_QUEUE: ", exc_info=True)
                    self.total_exceptions += 1
                    self.is_check_outbound = False
                    self.reset_radio()

                    self.event.wait(0.025)
                self.update_stats = True
                iodef.PWM_LED_GREEN.ChangeDutyCycle(0)
                iodef.PWM_LED_BLUE.ChangeDutyCycle(0)
                #GPIO.output(iodef.PIN_LED_GREEN, False)
                #GPIO.output(iodef.PIN_LED_BLUE, False)

                if isbeacon:
                    self.message.confirmed_beacon_sent()

    def check_irq(self,channel):
        if not self.ignore_radio_irq:
            self.txing = False 
            if self.is_check_outbound:
                self.event.wait(0.05)
            try:
                irq_flags = self.mc.get_irq_flags()

            except Exception, e:
                if self.radio_verbose > 0:
                    self.log.error("EXCEPTION GET_IRQ_FLAGS: ", exc_info=True)
                self.total_exceptions += 1

            else:
                if "RX_DONE" in irq_flags:
                    self.is_check_inbound = True

                if "TX_DONE" in irq_flags:
                    self.is_check_outbound = False
                    #self.total_sent += 1

                if "RESET" in irq_flags:
                    pass

    def reset_radio(self):
        self.ignore_radio_irq = True
        GPIO.output(iodef.PIN_RADIO_RESET, False)
        self.event.wait(0.1)
        GPIO.output(iodef.PIN_RADIO_RESET, True)
        self.event.wait(1)
        try:
            self.mc.clear_irq_flags()
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
        self.ignore_radio_irq = False

    def set_radio_recv_mode(self):
        self.event.wait(0.01)
        try:
            received_data = self.mc._send_command(OPCODES['PKT_RECV_CONT'])
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION PKT_RECV_CONT: ", exc_info=True)
        else:
            pass
        self.event.wait(0.01)
        try:
            pass
            self.mc.clear_irq_flags()
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
