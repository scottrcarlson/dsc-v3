#!/usr/bin/env python

from ll_ifc import ModuleConnection, OPCODES
import sys, time, binascii, struct, os
import RPi.GPIO as GPIO
import datetime
from threading import *
import iodef
from time import sleep
import time
import Queue
import logging

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
        self.prev_total_sent = 0
        self.prev_total_recv = 0
        self.prev_total_exceptions = 0

        self.last_tx = 0
        self.tx_throttle = 1 # Should we calculate based on rf parameters and packet size? YES
        self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
        self.tdma_frame = self.tdma_slot_width * self.config.tdma_total_slots

        self.is_check_outbound = False
        self.is_check_inbound = True
        self.update_stats = True
        self.mc = ModuleConnection(self.serial_device)

        self.reset_radio()
        GPIO.add_event_detect(iodef.PIN_RADIO_IRQ, GPIO.RISING, callback=self.check_irq, bouncetime=100)

        self.log.info('Initialized Radio Thread.')
        self.log.debug("Antenna Active:" + self.mc.get_antenna())
        self.config.freq, self.config.bandwidth, self.config.spread_factor, self.config.coding_rate, self.config.tx_power, self.config.sync_word = self.get_params()
        self.log.debug("Freq:" + str(self.config.freq) + " hz")
        self.log.debug("TX Power: " + str(self.config.tx_power) + " dBm")
        self.log.debug("Bandwidth:" + str(self.config.bandwidth))
        self.log.debug("SpreadFactor:" + str(self.config.spread_factor))
        self.log.debug("Coding Rate:" + str(self.config.coding_rate))
        self.log.debug("Sync Word:" + str(self.config.sync_word))

        self.config.update_bandwidth_eng()
        self.config.update_coding_rate_eng()

        self.ble_handset_rf_status_queue = Queue.Queue()
   
    def run(self):
        self.event.wait(1)
        last_checked_tdma = 0
        heartbeat_time = 0
        transmit_ok = False
        while not self.event.is_set():
            try:
                if time.time() - heartbeat_time > 5:
                    heartbeat_time = time.time()
                    if self.heartbeat.qsize() == 0:
                        self.heartbeat.put_nowait("hb")
                    if self.config.req_update_network:
                        self.config.req_update_network = False
                        self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
                        self.tdma_frame = self.tdma_slot_width * self.config.tdma_total_slots

                    if self.config.req_update_radio:
                        self.config.req_update_radio = False
                        self.set_params(self.config.freq, 
                                        self.config.bandwidth, 
                                        self.config.spread_factor, 
                                        self.config.coding_rate, 
                                        self.config.tx_power, 
                                        self.config.sync_word)
                        self.log.debug("Radio Settings Updated")
                elif time.time() - heartbeat_time < 0:
                    self.log.warn("Time changed to past. Re-initializing.")
                    heartbeat_time = time.time()

            except Exception as e:
                self.log.error(str(e))
            self.event.wait(0.05)

            try:
                if self.config.registered:
                    if self.is_check_inbound and not transmit_ok:# and not is_check_outbound:
                        self.process_inbound_msg()
                    elif transmit_ok and (time.time() - self.last_tx) > self.tx_throttle:
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

                    if (time.time() - last_checked_tdma) > 0.25: #Check to see if our TDMA Slot is Active
                        last_checked_tdma = time.time()
                        epoch = last_checked_tdma
                        tdma_frames_since_epoch = int(epoch / self.tdma_frame)

                        slot_start = (self.config.tdma_slot * self.tdma_slot_width) + (self.tdma_frame * tdma_frames_since_epoch)
                        slot_end = slot_start + self.tdma_slot_width

                        if (epoch > slot_start and epoch < (slot_end - self.config.tx_deadband)):
                            #self.log.debug("slot:" + str(self.config.tdma_slot) + " nodes:"+str(self.config.tdma_total_slots) + " txtime:" + str(self.config.tx_time)+" dband:"+str(self.config.tx_deadband))
                            self.message.is_radio_tx = True
                            if not transmit_ok:
                                self.message.generate_beacon()
                                self.log.debug("[TX mode] TDMA Slot Active")
                                #print "[TX mode] Packets Sent/Recvd/Error: [",self.total_sent,"]/[",self.total_recv,"]/[",self.total_exceptions,"]"
                            transmit_ok = True
                            self.ble_handset_rf_status_queue.queue.clear()
                            self.ble_handset_rf_status_queue.put_nowait([self.config.freq, True])
                        else:
                            self.message.is_radio_tx = False
                            if transmit_ok:
                                self.log.debug("[RX mode] Listening")
                                #print "[RX mode] Packets Sent/Recvd/Error: [",self.total_sent,"]/[",self.total_recv,"]/[",self.total_exceptions,"]"
                            transmit_ok = False
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

    def set_params(self,freq,bandwidth,spread_factor,coding_rate,tx_power,sync_word):
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
                    iodef.PWM_LED_RED.ChangeDutyCycle(5)
                    self.update_stats = True
                    msg = received_data[3:]
                    self.total_recv += 1

                    (rssi, ) = struct.unpack_from('<h', bytes(received_data[:2]))
                    snr = received_data[2] / 4.0

                    if self.config.registered:
                        self.message.radio_inbound_queue.put_nowait((rssi,snr,msg))
                    sleep(0.15)
                    #GPIO.output(iodef.PIN_LED_RED, False)
                    iodef.PWM_LED_RED.ChangeDutyCycle(0)
        finally:
            self.is_check_inbound = False

            try:
                self.mc.clear_irq_flags()
                sleep(0.05)

            except Exception, e:
                if self.radio_verbose > 0:
                    self.log.error( "EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)

    def process_outbound_msg(self):
        if not self.config.airplane_mode:
            outbound_data = ''
            isbeacon = False
            try:
                outbound_data = self.message.radio_beacon_queue.get_nowait()
                self.log.debug("Sending Beacon: " + str(self.message.radio_beacon_queue.qsize()))
                isbeacon = True
            except Queue.Empty:
                try:
                    outbound_data = self.message.radio_outbound_queue.get_nowait()
                    self.tx_throttle = ((1.0 / 510.0) * len(outbound_data)) + 0.3 #Scale found empiracaly (ie. no radio errors)
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
                try:
                    r = self.mc._send_command(OPCODES['PKT_SEND_QUEUE'], outbound_data)
                    sleep(0.025)
                    self.is_check_outbound = False

                except Exception, e:
                    if self.radio_verbose > 0:
                        self.log.error("EXCEPTION PKT_SEND_QUEUE: ", exc_info=True)
                    self.total_exceptions += 1
                    self.is_check_outbound = False
                    self.reset_radio()

                    sleep(0.025)
                self.update_stats = True
                iodef.PWM_LED_GREEN.ChangeDutyCycle(0)
                iodef.PWM_LED_BLUE.ChangeDutyCycle(0)
                #GPIO.output(iodef.PIN_LED_GREEN, False)
                #GPIO.output(iodef.PIN_LED_BLUE, False)

    def check_irq(self,channel):
        if not self.ignore_radio_irq:
            if self.is_check_outbound:
                sleep(0.05)
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
                    self.set_radio_recv_mode()
                    self.is_check_outbound = False
                    self.total_sent += 1

                if "RESET" in irq_flags:
                    pass

    def reset_radio(self):
        self.ignore_radio_irq = True
        GPIO.output(iodef.PIN_RADIO_RESET, False)
        sleep(0.1)
        GPIO.output(iodef.PIN_RADIO_RESET, True)
        sleep(1)
        try:
            self.mc.clear_irq_flags()
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
        self.ignore_radio_irq = False

    def set_radio_recv_mode(self):
        sleep(0.01)
        try:
            received_data = self.mc._send_command(OPCODES['PKT_RECV_CONT'])
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION PKT_RECV_CONT: ", exc_info=True)
        else:
            pass
        sleep(0.01)
        try:
            self.mc.clear_irq_flags()
        except Exception, e:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
