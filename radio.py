#!/usr/bin/env python

from ll_ifc import ModuleConnection, OPCODES
import time
import struct
import RPi.GPIO as GPIO
from threading import *
import iodef
import Queue
import logging
import random


class Radio(Thread):
    def __init__(self, serial_device, config, message, heartbeat):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()

        self.heartbeat = heartbeat
        # self.log.setLevel(logging.DEBUG)

        self.serial_device = serial_device
        self.config = config
        self.message = message

        self.ignore_radio_irq = False
        self.radio_verbose = 0

        self.total_recv = 0
        self.total_sent = 0
        self.total_exceptions = 0

        # Edge Detection
        self.prev_total_sent = 0
        self.prev_total_recv = 0
        self.prev_total_exceptions = 0
        self.prev_private_mode = -1

        self.is_radio_tx = False

        self.last_tx = 0
        self.tx_throttle = 0  # We are limited by efficiency of processing inbound packets.
        self.frame_config_width = 2  # n seconds at the beginning of frame to allow for configuration changes
        self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
        self.tdma_frame_width = (self.tdma_slot_width * self.config.tdma_total_slots) + self.frame_config_width

        self.vchannel_freq = 0

        self.transmit_timeout = 1
        self.mc = ModuleConnection(self.serial_device)

        self.reset_radio()

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
        last_checked_tdma = time.time()
        heartbeat_time = 0
        prev_epoch_tdma_frames = 0
        chkcfg_time = 0
        while not self.event.is_set():
            self.event.wait(0.01)
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

            try:
                if self.config.registered and not self.config.airplane_mode:
                    if not self.is_radio_tx:
                        self.process_inbound_msg()
                    elif self.is_radio_tx and (time.time() - self.last_tx) > self.tx_throttle:
                        self.last_tx = time.time()
                        self.process_outbound_msg()
                    if time.time() - self.last_tx < 0:
                        self.log.warn("Time changed to past. Re-initializing.")
                        self.last_tx = time.time()

                    # if self.total_sent != self.prev_total_sent or self.total_recv != self.prev_total_recv or self.total_exceptions != self.prev_total_exceptions:
                    #    self.prev_total_sent = self.total_sent
                    #    self.prev_total_recv = self.total_recv
                    #    self.prev_total_exceptions = self.total_exceptions
                        # print "== Sent: [",self.total_sent,"]  Recvd:[",self.total_recv,"] Radio Exceptions:[",self.total_exceptions,"] =="

                    if (time.time() - last_checked_tdma) > 0.1:  # Check to see if our TDMA Slot is Active
                        last_checked_tdma = time.time()

                        if self.prev_private_mode != self.message.private_mode:
                            self.prev_private_mode = self.message.private_mode
                            if self.message.private_mode == self.message.PRIVATE_MODE_DISABLED:
                                tdma_slot = self.config.tdma_slot
                                tdma_total_slots = self.config.tdma_total_slots
                                self.tdma_slot_width = self.config.tx_time + self.config.tx_deadband
                            elif self.message.private_mode == self.message.PRIVATE_MODE_PRIMARY:
                                tdma_slot = 0
                                tdma_total_slots = 2
                                self.tdma_slot_width = self.config.e_tx_time + self.config.e_tx_deadband
                            elif self.message.private_mode == self.message.PRIVATE_MODE_SECONDARY:
                                tdma_slot = 1
                                tdma_total_slots = 2
                                self.tdma_slot_width = self.config.e_tx_time + self.config.e_tx_deadband
                        epoch = last_checked_tdma
                        
                        epoch_tdma_frames = int(epoch / self.tdma_frame_width)
                        # epoch_tdma_frame_age = (epoch / self.tdma_frame_width) % epoch_tdma_frames
                        if epoch_tdma_frames != prev_epoch_tdma_frames:  # and epoch_tdma_frame_age < 0.75:
                            prev_epoch_tdma_frames = epoch_tdma_frames

                            # New TDMA Frame, check and set network configuration
                            if self.message.private_mode != self.message.PRIVATE_MODE_DISABLED:
                                random.seed(self.config.netkey + self.config.e_ch_seed + str(epoch_tdma_frames))
                                self.vchannel_freq = int(str(int(random.uniform(90250000, 92750000))).ljust(9, '0'))
                                self.log.debug("Private Virtual Channel: {" + str(self.vchannel_freq) + "} hz @ " + str(self.message.calculate_bitrate(self.config.e_spread_factor, self.config.e_bandwidth, self.config.e_coding_rate)) + " kbps")
 
                                try:
                                    self.set_params(self.vchannel_freq,
                                                    self.config.e_bandwidth,
                                                    self.config.e_spread_factor,
                                                    self.config.e_coding_rate,
                                                    self.config.e_tx_power,
                                                    self.config.sync_word,
                                                    False)
                                except Exception:
                                    self.log.error("IO Error from Radio Module")

                            else:
                                random.seed(self.config.netkey + str(epoch_tdma_frames))
                                self.vchannel_freq = int(str(int(random.uniform(90250000, 92750000))).ljust(9, '0'))
                                self.log.debug("Main Virtual Channel: {" + str(self.vchannel_freq) + "} hz @ " + str(self.message.calculate_bitrate(self.config.spread_factor, self.config.bandwidth, self.config.coding_rate)) + " kbps")
                                try:
                                    self.set_params(self.vchannel_freq,
                                                    self.config.bandwidth,
                                                    self.config.spread_factor,
                                                    self.config.coding_rate,
                                                    self.config.tx_power,
                                                    self.config.sync_word,
                                                    False)
                                except Exception:
                                    self.log.error("IO Error from Radio Module")
  


                        self.tdma_frame_width = (self.tdma_slot_width * tdma_total_slots) + self.frame_config_width
                        slot_start = self.frame_config_width + (tdma_slot * self.tdma_slot_width) + (self.tdma_frame_width * epoch_tdma_frames)
                        slot_end = slot_start + self.tdma_slot_width
                        
                        if epoch > slot_start and epoch < (slot_end - self.config.tx_deadband):
                            if not self.is_radio_tx:
                                self.is_radio_tx = True
                                if self.message.private_mode != self.message.PRIVATE_MODE_DISABLED:
                                    packet_cnt = self.message.fill_outbound_queue()
                                    bs_kb = round((packet_cnt * 224) / 1000.0, 2)
                                    self.log.debug(str(packet_cnt) + " packets left to transmit [" + str(bs_kb) + " kB]")
                                    for node in self.message.disregard_list:
                                        self.log.debug(node + ": " + str(len(self.message.disregard_list[node])) + " acknowledged")
                                self.message.generate_beacon()
                                # self.log.debug("[TX mode] Transmitting")
                            
                            self.ble_handset_rf_status_queue.queue.clear()
                            self.ble_handset_rf_status_queue.put_nowait([self.config.freq, True])
                        else:
                            if self.is_radio_tx:
                                self.is_radio_tx = False
                                # self.log.debug("[RX mode] Listening")
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

    def set_params(self, freq, bandwidth, spread_factor, coding_rate, tx_power, sync_word, enable_store):
        flags = 255
        parm1 = 0
        parm1 |= ((spread_factor - 6) & 0x07) << 4
        parm1 |= ((coding_rate - 1) & 0x03) << 2
        parm1 |= bandwidth & 0x03
        parm2 = 0b11  # Header Enabled / CRC Enabled / IRQ not Inverted
        preamble_syms = 6
        parm3 = (preamble_syms >> 8) & 0xFF
        parm4 = (preamble_syms >> 0) & 0xFF
        parm5 = (freq >> 24) & 0xFF
        parm6 = (freq >> 16) & 0xFF
        parm7 = (freq >> 8) & 0xFF
        parm8 = freq & 0xFF

        params = bytearray([flags, parm1, parm2, parm3, parm4, parm5, parm6, parm7, parm8])
        self.mc._send_command(OPCODES['SET_RADIO_PARAMS'], params)
        self.mc._send_command(OPCODES['TX_POWER'], bytearray([tx_power]))
        self.mc._send_command(OPCODES['SYNC_WORD_SET'], bytearray([sync_word]))
        
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



    def process_inbound_msg(self):
        global total_recv
        global total_exceptions

        self.event.wait(0.01)
        flags = self.mc.get_irq_flags()
        # print flags

        received_data = None
        try:
            if 'RX_DONE' in flags:
                self.mc.clear_irq_flags(['RX_DONE'])
                received_data = self.mc._send_command(OPCODES['PKT_RECV_CONT'])
                if received_data is None:
                    self.log.warning("RX_DONE flag set but no packet available.")

        except Exception:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION PKT_RECV_CONT: ", exc_info=True)

        else:
            if not self.config.airplane_mode:
                if received_data is not None:
                    iodef.PWM_LED_RED.ChangeDutyCycle(5)
   
                    msg = received_data[3:]
                    self.total_recv += 1

                    try:
                        (rssi, ) = struct.unpack_from('<h', bytes(received_data[:2]))
                        snr = received_data[2] / 4.0
                    except Exception:
                        print "RX unpack error"
                    else:
                        if self.config.registered:
                            self.message.radio_inbound_queue.put_nowait((rssi, snr, str(msg)))

                    iodef.PWM_LED_RED.ChangeDutyCycle(0)

    def process_outbound_msg(self):
        if not self.config.airplane_mode:
            outbound_data = ''
            isbeacon = False
            try:
                outbound_data = self.message.radio_beacon_queue.get_nowait()
                isbeacon = True
            except Queue.Empty:
                try:
                    outbound_data = self.message.radio_outbound_queue.get_nowait()
                except Queue.Empty:
                    pass
            if outbound_data != '':
                if isbeacon:
                    iodef.PWM_LED_BLUE.ChangeDutyCycle(5)
                    # self.log.debug("Sending Beacon")
                else:
                    iodef.PWM_LED_GREEN.ChangeDutyCycle(5)
                    # self.log.debug("Sending Msg")

                try:
                    self.mc._send_command(OPCODES['PKT_SEND_QUEUE'], outbound_data)

                except Exception:
                    if self.radio_verbose > 0:
                        self.log.error("EXCEPTION PKT_SEND_QUEUE: ", exc_info=True)
                    self.total_exceptions += 1
                    self.reset_radio()

                self.wait_for_flags(['TX_DONE'], self.transmit_timeout, bad_flags=['TX_ERROR'])
                iodef.PWM_LED_GREEN.ChangeDutyCycle(0)
                iodef.PWM_LED_BLUE.ChangeDutyCycle(0)

                if isbeacon:
                    self.message.confirmed_beacon_sent()

    def wait_for_flags(self, flags, timeout, bad_flags=None):
        """ Waits for all flags in `flags` to show up. """
        start = time.time()
        while time.time() - start < timeout:
            mod_flags = self.mc.get_irq_flags()
            if bad_flags:
                for flag in bad_flags:
                    if flag in mod_flags:
                        self.log.error("Bad Flag found: " + flag)
            if all(f in mod_flags for f in flags):
                break
            else:
                self.event.wait(0.1)
        else:
            self.log.error("Timeout waiting for flags {}".format(flags))

    def reset_radio(self):
        self.log.debug("Resetting Radio Module")
        self.ignore_radio_irq = True
        GPIO.output(iodef.PIN_RADIO_RESET, False)
        self.event.wait(0.1)
        GPIO.output(iodef.PIN_RADIO_RESET, True)
        self.event.wait(1)
        try:
            self.mc.clear_irq_flags()
        except Exception:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
        self.ignore_radio_irq = False

    def set_radio_recv_mode(self):
        self.event.wait(0.01)
        try:
            self.mc._send_command(OPCODES['PKT_RECV_CONT'])
        except Exception:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION PKT_RECV_CONT: ", exc_info=True)
        else:
            pass
        self.event.wait(0.01)
        try:
            pass
            self.mc.clear_irq_flags()
        except Exception:
            if self.radio_verbose > 0:
                self.log.error("EXCEPTION: CLEAR_IRQ_FLAGS: ", exc_info=True)
