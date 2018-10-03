#!/usr/bin/env python
import time
from threading import *
import Queue
import hashlib
import logging
import struct
import base64
import uuid
import re
import traceback
import os
import math

# Message thread is responsible for producing and consuming inbound/outbound radio packets via Queues
# Perodically fill outbound queue with packets on the repeat list
# Processing Packets / Validating / De-Duping


class Message(Thread):
    def __init__(self, crypto, config, heartbeat):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()
        self.heartbeat = heartbeat

        self.config = config
        self.crypto = crypto

        self.MSG_TYPE_MESSAGE = 1
        self.MSG_TYPE_BEACON = 2
        self.MSG_TYPE_BEACON_ENGAGE = 3
        self.MSG_TYPE_ACK_REQ = 4
        self.MSG_TYPE_ACK = 5
        self.MSG_TYPE_NACK = 6
        self.MSG_TYPE_ECHO_REQ = 7
        self.MSG_TYPE_SYNC_DISREGARD = 8

        self.packet_ttl = 300

        self.compose_msg = ""
        self.network_plaintexts = []
        self.group_cleartexts = []
        self.peer_uuid = ""
        self.beacon_ack_list = []
        self.beacon_hash = ""
        self.beacons_recvd = {}
        self.beacon_type = self.MSG_TYPE_BEACON
        self.engage_ignore_list = []

        self.repeat_msg_index = 0
        self.repeat_msg_list = []
        self.disregard_list = {}

        self.radio_inbound_queue = Queue.Queue()
        self.radio_outbound_queue = Queue.Queue()
        self.radio_beacon_queue = Queue.Queue()
        self.ble_handset_msg_queue = Queue.Queue()

        self.PRIVATE_MODE_DISABLED = 0
        self.PRIVATE_MODE_PRIMARY = 1
        self.PRIVATE_MODE_SECONDARY = 2
        self.private_mode = self.PRIVATE_MODE_DISABLED
        self.prev_private_mode = self.PRIVATE_MODE_DISABLED
        self.private_mode_send_flag = False
        self.private_mode_timeout = 15
        self.private_mode_time = 0
        self.private_mode_disabled_req = False
        self.private_session_time = 0
        self.log.info("Initialized Message Thread.")

        self.test_echo_cnt = 0
        self.echo_mode = True

        self.test_message_file = open('/dscdata/messages', 'a+', 0)

    def run(self):
        self.event.wait(1)

        self.beacon_hash = hashlib.md5(
            "".join(str(x) for x in sorted(
                self.repeat_msg_list))).hexdigest().ljust(32)

        while not self.event.is_set():
            try:
                if self.heartbeat.qsize() == 0:
                    self.heartbeat.put_nowait("hb")
                try:
                    packet = self.radio_inbound_queue.get_nowait()
                except Queue.Empty:
                    pass
                else:
                    rssi, snr, msg = packet
                    self.process_inbound_packet(msg, rssi, snr)

                if self.prev_private_mode != self.private_mode:
                    self.prev_private_mode = self.private_mode
                    self.private_mode_time = time.time()
                    self.radio_outbound_queue.queue.clear()
                    if self.private_mode == self.PRIVATE_MODE_DISABLED:
                        self.log.debug("Transfer time: " + str(time.time() - self.private_session_time))
                    else:
                        self.private_session_time = time.time()

                if self.private_mode != self.PRIVATE_MODE_DISABLED:
                    if time.time() > self.private_mode_time + self.private_mode_timeout:
                        self.private_mode = self.PRIVATE_MODE_DISABLED
                        self.log.debug("Ch Time-out. Return to Main Ch")

            except Exception:
                traceback.print_exc()

            if self.config.test_mode:
                self.check_for_test_messages()
            self.event.wait(0.05)

    def stop(self):
        self.log.info("Stopping Message Thread.")
        self.event.set()

    def fill_outbound_queue(self):
        # self.radio_outbound_queue.queue.clear()
        if self.radio_outbound_queue.qsize() == 0:
            for msg_uuid, msg in self.repeat_msg_list:
                if msg_uuid not in self.disregard_list:
                    self.radio_outbound_queue.put_nowait(msg)
                else:
                    if self.peer_uuid not in self.disregard_list[msg_uuid]:
                        self.radio_outbound_queue.put_nowait(msg)
        return self.radio_outbound_queue.qsize()

    def update_disregard(self,msg_uuid, node_uuid, peer_uuid):
        # ---------------
        # Prevent sending messages to nodes that already have them
        # ---------------
        if msg_uuid in self.disregard_list:
            self.disregard_list[msg_uuid].append(node_uuid) if node_uuid not in self.disregard_list[msg_uuid] else None
            self.disregard_list[msg_uuid].append(peer_uuid) if peer_uuid not in self.disregard_list[msg_uuid] else None
        else:
            self.disregard_list[msg_uuid] = [node_uuid, peer_uuid]

    def generate_beacon(self):
        if self.config.registered and not self.config.airplane_mode:
            if self.beacon_type == self.MSG_TYPE_BEACON_ENGAGE:
                if self.private_mode == self.PRIVATE_MODE_DISABLED:
                    # self.log.debug("Sending Engagement Req")
                    self.process_outbound_packet(self.beacon_type)
            elif self.beacon_type == self.MSG_TYPE_ACK:
                # self.log.debug("Sending Ack Response")
                self.process_outbound_packet(self.beacon_type)
            elif self.beacon_type == self.MSG_TYPE_SYNC_DISREGARD:
                print "sync disregard"
                self.process_outbound_packet(self.beacon_type)
            else:
                # self.log.debug("Sending Beacon")
                self.process_outbound_packet(self.beacon_type)

    def confirmed_beacon_sent(self):
        # Radio thread reporting beacons
        if self.beacon_type == self.MSG_TYPE_BEACON_ENGAGE:
            self.log.debug("Engage Beacon Sent. Switching to Private Ch")
            self.config.req_update_network = True
            self.private_mode = self.PRIVATE_MODE_SECONDARY
            self.private_mode_send_flag = False
        elif self.beacon_type == self.MSG_TYPE_ACK_REQ:
            self.private_mode_send_flag = False
        elif self.beacon_type == self.MSG_TYPE_ACK:
            self.beacon_ack_list = []
            self.private_mode_send_flag = False
        elif self.beacon_type == self.MSG_TYPE_SYNC_DISREGARD:
            pass
        if self.private_mode_disabled_req:
            self.private_mode_disabled_req = False
            self.private_mode = self.PRIVATE_MODE_DISABLED
            # self.log.debug("Done. Leaving Private Channel")
        self.beacon_type = self.MSG_TYPE_BEACON

    def add_msg_to_repeat_list(self, msg_uuid, msg):
        if not self.check_for_dup(msg, self.repeat_msg_list):
            self.repeat_msg_list.append([msg_uuid, msg])
            self.beacon_hash = hashlib.md5(
                "".join(str(x) for x in sorted(
                    self.repeat_msg_list))).hexdigest().ljust(32)

            # self.log.debug("Adding unique msg to repeat list.")
            return True
        else:
            return False

    def check_for_dup(self, msg, msglist):
        for m in msglist:
            if msg == m[1]:
                return True
        return False

    def check_for_dup2(self, msg, msglist):
        for m in msglist:
            if msg == m:
                return True
        return False

    def process_outbound_packet(self, msg_type, msg=""):
        if msg_type == self.MSG_TYPE_BEACON:
            #     Beacon Packet
            #     8 bytes msg author
            #     8 bytes node uuid
            #     32 bytes md5 hash of all ota_ciphers in repeat_list
            #
            #     Total 48 bytes for a beacon packet
            ##################
            group_cleartext = (self.config.alias.ljust(8) +
                               self.config.node_uuid.ljust(8) +
                               self.beacon_hash)

        elif msg_type == self.MSG_TYPE_ACK:
            #     Ack Packet
            #     8 bytes msg author
            #     8 bytes node uuid
            #     ##32 bytes md5 hash of all ota_ciphers in repeat_list
            #
            #     Total 64 + (ack * 8) bytes for a beacon packet
            ##################
            uuid_ack_str1 = "".join(self.beacon_ack_list)[:144]
            uuid_ack_str2 = "".join(self.beacon_ack_list)[144:288]
            uuid_ack_str3 = "".join(self.beacon_ack_list)[288:432]

            group_cleartext_list = []
            if len(uuid_ack_str1) > 0:
                group_cleartext_list.append(self.config.alias.ljust(8) +
                                            self.config.node_uuid.ljust(8) +
                                            uuid_ack_str1)
            if len(uuid_ack_str2) > 0:
                group_cleartext_list.append(self.config.alias.ljust(8) +
                                            self.config.node_uuid.ljust(8) +
                                            uuid_ack_str2)
            if len(uuid_ack_str3) > 0:
                group_cleartext_list.append(self.config.alias.ljust(8) +
                                            self.config.node_uuid.ljust(8) +
                                            uuid_ack_str3)

        elif msg_type == self.MSG_TYPE_SYNC_DISREGARD:
            #     Sync Disregard Packet
            #     8 bytes msg author
            #     8 bytes node uuid
            #
            #     Total 16 +
            ##################
            group_cleartext = (self.config.alias.ljust(8) +
                               self.config.node_uuid.ljust(8) +
                               "".join(self.beacon_ack_list))


        elif msg_type == self.MSG_TYPE_MESSAGE or msg_type == self.MSG_TYPE_ECHO_REQ:
            #     Group Message Packet
            #     8 bytes msg author
            #     8 bytes node uuid
            #     159 bytes for message
            #
            #     Total 175 bytes
            ###################
            if len(msg) > 159:
                self.log.error("Rejected " + str(len(msg)) + " byte msg. Max 159 bytes")
                return False

            group_cleartext = self.config.alias.ljust(8) + self.config.node_uuid.ljust(8) + msg

        elif msg_type == self.MSG_TYPE_BEACON_ENGAGE:
            #     Engage Request Packet
            #     8 bytes node uuid
            #     8 bytes peer uuid
            #     2 bytes channel seed
            #     1 byte transmit power
            #     1 byte bandwidth
            #     1 byte spread factor
            #     1 byte coding rate
            #     1 byte tx time
            #     1 byte tx time deadband
            #
            #     Total 24 bytes for a beacon packet
            ##################
            self.config.e_ch_seed = str(uuid.uuid4())[:2]
            self.config.e_tx_power = 20
            self.config.e_bandwidth = 3
            self.config.e_spread_factor = 8
            self.config.e_coding_rate = 2
            self.config.e_tx_time = 3
            self.config.e_tx_deadband = 2

            group_cleartext = (self.config.node_uuid.ljust(8) +
                               self.peer_uuid.ljust(8) +
                               self.config.e_ch_seed +
                               chr(self.config.e_tx_power) +
                               chr(self.config.e_bandwidth) +
                               chr(self.config.e_spread_factor) +
                               chr(self.config.e_coding_rate) +
                               chr(self.config.e_tx_time) +
                               chr(self.config.e_tx_deadband))

        # Engagement Request Responder is TDMA Slot 0 in a new 2 node network
        # if another node sees a beacon response then it will not respond
        # to that beacon and try another available beacon
        # the originator of the beacon handles the first come/first serve basis

        group_cipher_list = []
        if msg_type == self.MSG_TYPE_ACK:
            for msg in group_cleartext_list:
                group_cipher_list.append(
                    self.crypto.encrypt(str(self.config.groupkey), msg))
        else:
            group_cipher = self.crypto.encrypt(
                str(self.config.groupkey), group_cleartext)
        # Network Message Packet
        # 4 bytes for sent time in epoch seconds
        # 4 bytes TTL in seconds
        # 3 bytes system id
        # 8 bytes beacon uuid
        # 1 byte  msg type
        # ?? byte group cipher
        # Total ?? bytes OTA message packet
        timestamp = struct.pack(">I", time.time())
        ttl = struct.pack(">I", self.packet_ttl)

        ota_cipher_list = []
        if msg_type == self.MSG_TYPE_ACK:
            for g_cipher in group_cipher_list:
                msg_uuid = str(uuid.uuid4())[:8]
                network_plaintext = timestamp + ttl + 'DSC' + msg_uuid + str(msg_type) + g_cipher
                ota_cipher_list.append(self.crypto.encrypt(str(self.config.netkey), network_plaintext))
        else:
            msg_uuid = str(uuid.uuid4())[:8]
            network_plaintext = timestamp + ttl + 'DSC' + msg_uuid + str(msg_type) + group_cipher
            ota_cipher = self.crypto.encrypt(str(self.config.netkey), network_plaintext)

        # self.log.debug(str(len(ota_cipher)))
        if msg_type == self.MSG_TYPE_MESSAGE or msg_type == self.MSG_TYPE_ECHO_REQ:
            if self.add_msg_to_repeat_list(msg_uuid, ota_cipher):
                if self.config.hw_rev <= 2:
                    self.network_plaintexts.append(network_plaintext)
                    self.process_group_messages()

        elif msg_type == self.MSG_TYPE_ACK:
            # self.log.debug("Ack Added to Queue.")
            self.radio_beacon_queue.queue.clear()
            for ota_cipher in ota_cipher_list:
                self.radio_beacon_queue.put_nowait(ota_cipher)

        elif msg_type == self.MSG_TYPE_BEACON or self.MSG_TYPE_BEACON_ENGAGE or self.MSG_TYPE_ACK_REQ:
            # self.log.debug("Beacon Added to Queue.")
            self.radio_beacon_queue.queue.clear()
            self.radio_beacon_queue.put_nowait(ota_cipher)

        return True  # TODO Lets capture crypto error and report back false


    def process_inbound_packet(self, ota_cipher, rf_rssi, rf_snr):
        # self.log.debug("Processing Inbound Packet")
        # self.log.debug("Processing Network Message.. ") #RSSI/SNR: " + rf_rssi + "/" + rf_snr)
        # self.log.debug("key:" + self.network_key + " size:" + str(len(self.network_key)))
        if self.private_mode != self.PRIVATE_MODE_DISABLED:
            self.private_mode_time = time.time()

        try:
            network_plaintext = self.crypto.decrypt(str(self.config.netkey), ota_cipher)
        except Exception:
            self.log.debug("Failed to decrypt packet.")
            traceback.print_exc()
        else:
            # self.log.debug("network plaintext:" + binascii.hexlify(network_plaintext))
            # self.log.debug("netkey len: " + str(len(self.config.netkey)) + " grpkey len:" + str(len(self.config.groupkey)))
            if 'DSC' in network_plaintext:
                # self.log.debug("check: %s (%d)" % (binascii.hexlify(network_plaintext), len(network_plaintext)))
                packet_sent_time = struct.unpack(">I", network_plaintext[:4])[0]  # unpack() always returns a tuple
                packet_ttl = struct.unpack(">I", network_plaintext[4:8])[0]  # unpack() always returns a tuple
                system_id = network_plaintext[8:11]
                msg_uuid = network_plaintext[11:19]
                try:
                    msg_type = int(network_plaintext[19:20])
                except Exception:
                    print "************* Garbled Message?"
                    return False

                group_cipher = network_plaintext[20:]
                group_cleartext = self.crypto.decrypt(str(self.config.groupkey), group_cipher)
                packet_author = group_cleartext[:8].strip()
                node_uuid = group_cleartext[8:16]

                if msg_type == self.MSG_TYPE_MESSAGE or msg_type == self.MSG_TYPE_ECHO_REQ:
                    group_msg = group_cleartext[16:]

                    if node_uuid == '':
                            self.log.error("???????????? empty uuid: " + node_uuid + " peeruuid: " + self.peer_uuid)
                    else:
                        if not self.add_msg_to_repeat_list(msg_uuid, ota_cipher):
                            self.log.debug("Dropping inbound dup " + str(msg_uuid))
                            if self.private_mode != self.PRIVATE_MODE_DISABLED:
                                self.beacon_type = self.MSG_TYPE_ACK
                                if not self.check_for_dup2(msg_uuid, self.beacon_ack_list):
                                    self.beacon_ack_list.append(msg_uuid)
                            return False

                        self.update_disregard(msg_uuid, node_uuid, self.peer_uuid)

                        if not self.check_for_dup2(msg_uuid, self.beacon_ack_list):
                            self.beacon_ack_list.append(msg_uuid)
                        # ----------------

                        if self.config.hw_rev <= 2:
                            if network_plaintext not in self.network_plaintexts:
                                self.network_plaintexts.append(network_plaintext)
                                self.process_group_messages()

                        self.ble_handset_msg_queue.put_nowait([packet_author,
                                                               node_uuid,
                                                               group_msg,
                                                               base64.encodestring(network_plaintext),
                                                               packet_sent_time,
                                                               packet_ttl,
                                                               msg_type,
                                                               rf_rssi,
                                                               rf_snr])
                        #if self.config.test_mode:
                            #self.test_message_file.write("+_+_+_+_+_+_+_+_+\n")
                            #self.test_message_file.write(packet_author + " / [" + node_uuid + "]\n")
                            #self.test_message_file.write(group_msg + "\n")

                        if msg_type == self.MSG_TYPE_ECHO_REQ:
                            self.test_echo_cnt += 1
                            self.process_outbound_packet(self.MSG_TYPE_MESSAGE, group_msg + " [count:" + str(self.test_echo_cnt) + "]")
                        self.log.debug("Recv New msg %s q:%s Peer:%s " %
                                        (msg_uuid, self.signal_quality(rf_rssi, rf_snr), node_uuid))
                    self.beacon_type = self.MSG_TYPE_ACK

                elif msg_type == self.MSG_TYPE_BEACON:
                    beacon_hash = group_cleartext[16:48]

                    # Check beacon hash to see if it does not matches with ours
                    if beacon_hash != self.beacon_hash and self.private_mode == self.PRIVATE_MODE_DISABLED:
                        # Flag beacon engagement on the next tdma cycle
                        if node_uuid not in self.engage_ignore_list:
                            self.peer_uuid = node_uuid
                            self.beacon_type = self.MSG_TYPE_BEACON_ENGAGE
                        else:
                            self.engage_ignore_list.remove(node_uuid)

                    if self.private_mode == self.PRIVATE_MODE_DISABLED:
                        self.beacon_ack_list = []
                                                   
                    if beacon_hash == self.beacon_hash:
                        if node_uuid == "" or self.peer_uuid == "":
                            pass
                            #self.log.error("!!!!!!!!!!! empty uuid nodeuuid: " + node_uuid + " peeruuid: " + self.peer_uuid)
                        else:
                            for (msg_uuid, msg) in self.repeat_msg_list:
                                self.update_disregard(msg_uuid, node_uuid, self.peer_uuid)

                        if self.private_mode != self.PRIVATE_MODE_DISABLED:
                            self.private_mode_disabled_req = True


                    self.beacons_recvd[packet_author] = (packet_sent_time, rf_rssi, rf_snr)
                    self.ble_handset_msg_queue.put_nowait([packet_author,
                                                           node_uuid,
                                                           "",
                                                           base64.encodestring(network_plaintext),
                                                           packet_sent_time,
                                                           packet_ttl,
                                                           msg_type,
                                                           rf_rssi,
                                                           rf_snr])

                    self.log.debug("Recv Beacon q:%s Peer:%s RepeatSt:%s " %
                                   (self.signal_quality(rf_rssi, rf_snr), node_uuid, beacon_hash[:8]))

                elif msg_type == self.MSG_TYPE_ACK:
                    msg_uuids = re.findall('........', group_cleartext[16:])
                    if node_uuid == "" or self.peer_uuid == "":
                        self.log.error("************ empty uuid nodeuuid: " + node_uuid + " peeruuid: " + self.peer_uuid)
                    else:   
                        for msg_uuid in msg_uuids:
                            self.update_disregard(msg_uuid, node_uuid, self.peer_uuid)

                    self.log.debug("Recv ACK q:%s Peer:%s RepeatSt: " %
                                   (self.signal_quality(rf_rssi, rf_snr), node_uuid))

                elif msg_type == self.MSG_TYPE_BEACON_ENGAGE:
                    peer_uuid = group_cleartext[:8]
                    if node_uuid == self.config.node_uuid:
                        self.engage_ignore_list = []
                        #   Engage Request Packet
                        #     8 bytes peer uuid (them)
                        #     8 bytes node uuid (us)
                        #     2 bytes channel seed
                        #     1 byte transmit power
                        #     1 byte bandwidth
                        #     1 byte spread factor
                        #     1 byte coding rate
                        #     1 byte tx time
                        #     1 byte tx time deadband
                        self.peer_uuid = peer_uuid
                        ch_seed = group_cleartext[16:18]
                        tx_power = ord(group_cleartext[18:19])
                        bw = ord(group_cleartext[19:20])
                        sf = ord(group_cleartext[20:21])
                        cr = ord(group_cleartext[21:22])
                        tx_time = ord(group_cleartext[22:23])
                        tx_deadband = ord(group_cleartext[23:24])

                        self.log.debug("Recv Engage Req q:%s Peer: %s Channel Seed:%s bw:%d sf: %d cr: %d txsec:%d txdbsec:%d pow:%d" %
                                       (self.signal_quality(rf_rssi, rf_snr), self.peer_uuid, ch_seed, bw, sf, cr, tx_time, tx_deadband, tx_power))
                    
                        # Process/Execute Engagement
                        self.config.e_ch_seed = ch_seed
                        self.config.e_tx_power = tx_power
                        self.config.e_bandwidth = bw
                        self.config.e_spread_factor = sf
                        self.config.e_coding_rate = cr
                        self.config.e_tx_time = tx_time
                        self.config.e_tx_deadband = tx_deadband
                        self.config.req_update_network = True
                        self.private_mode = self.PRIVATE_MODE_PRIMARY
                        # self.private_mode_send_flag = True

                    else:
                        # This is for someone else, we will not engage peer_uuid this round
                        # Unless there is a opportunity to "tag along" in a listen only mode (3 node network, TODO examples)
                        self.log.debug("Recv Engage Req: Ignored. UUID: " + node_uuid + " not our UUID: " + self.config.node_uuid)
                        self.beacon_type = self.MSG_TYPE_BEACON
                        self.engage_ignore_list.append(node_uuid)
                        self.engage_ignore_list.append(peer_uuid)
                    
                    
                    pass
                else:
                    self.log.warn("Unknown Msg Type: " + group_cleartext + " MsgType: " + str(msg_type))
            else:
                self.log.debug("Packet Dropped due to missing MAC")

    def process_group_messages(self):
        # self.log.debug("Processing Group Message")
        self.group_cleartexts = []
        for network_plaintext in self.network_plaintexts:
            packet_sent_time = struct.unpack(">I", network_plaintext[:4])[0]  # unpack() always returns a tuple
            packet_ttl = struct.unpack(">I", network_plaintext[4:8])[0]  # unpack() always returns a tuple
            system_id = network_plaintext[8:11]
            msg_uuid = network_plaintext[11:19]
            msg_type = int(network_plaintext[19:20])
            group_cipher = network_plaintext[20:]
            group_cleartext = self.crypto.decrypt(str(self.config.groupkey), group_cipher)

            packet_author = group_cleartext[:8].strip()
            node_uuid = group_cleartext[8:16]
            group_msg = group_cleartext[16:]
            age_sec = time.time() - packet_sent_time
            if age_sec < 60:
                time_since = "now|"
            else:
                time_since = str(int(age_sec / 60)) + "m|"
            # self.group_cleartexts.append(datetime.datetime.fromtimestamp(float(packet_sent_time)).strftime("%m-%d %H:%M"))
            self.group_cleartexts.append(packet_author + '|' + time_since + group_msg)
            # self.log.debug("GroupText Len: " +  str(len(self.group_cleartexts)))
        return True


    def calculate_bitrate(self, sf, bw, cr):
        if cr == 1:
            cr = 4.0 / 5.0
        elif cr == 2:
            cr = 4.0 / 6.0
        elif cr == 3:
            cr = 4.0 / 7.0
        elif cr == 4:
            cr = 4.0 / 8.0

        if bw == 0:
            bw = 62.5
        elif bw == 1:
            bw = 125.0
        elif bw == 2:
            bw = 250.0
        elif bw == 3:
            bw = 500.0

        bitrate = sf * (bw / math.pow(2, sf) * cr)
        return round(bitrate, 2)

    def signal_quality(self, rssi, snr):
        # References
        # https://www.semtech.com/uploads/documents/sx1272.pdf

        # Strong signals with SNR > 7: RSSI is informant
        # Weak signals with SNR < 7: SNR is informant (Also SNR SF Limits are appoaching link failure)
        # Spreadfactor vs rssi/snr
        # SF7 RSSI > -123 / SNR > -7.5
        # SF8 RSSI > -126 / SNR > -10.
        # SF9 RSSI > -129 / SNR > -12.5
        # SF10 RSSI > -132 / SNR > -15
        # SF11 RSSI > -134 / SNR > -17.5
        # SF12 RSSI > -137 / SNR > -20
        # Look at these ratings, are they reasonable?
        # print str(rssi) + " " +str(snr)
        sf = self.config.spread_factor
        cr = self.config.coding_rate
        bw = self.config.bandwidth
        if self.private_mode != self.PRIVATE_MODE_DISABLED:
            sf = self.config.e_spread_factor
            cr = self.config.e_coding_rate
            bw = self.config.e_bandwidth

        # Based on BW 125khz
        if sf == 7:
            snr_limit = -7.5
        elif sf == 8:
            snr_limit = -10
        elif sf == 9:
            snr_limit = -12.5
        elif sf == 10:
            snr_limit = -15
        elif sf == 11:
            snr_limit = -17.5
        elif sf == 12:
            snr_limit = -20

        if snr < 0:
            quality_value = rssi + (snr * 0.25)
        else:
            rssi = (16 / 15) * rssi
            quality_value = rssi * 0.25

        # self.log.debug("Quality Value: " + str(quality_value) + " RSSI / SNR: " + str(rssi) + " / " + str(snr))
        
        # Completely made up
        if quality_value > -10:
                quality = "GREAT"
        elif quality_value > -40:
                quality = "GOOD"
        elif quality_value > -80:
                quality = "OK"
        elif quality_value > -120:
                quality = "POOR"
        else:
                quality = "BAD"


        return quality

    def check_for_test_messages(self):
        try:
            if os.path.isfile("/dscdata/sendmsg"):
                self.log.debug("Test Message File Modified")
                msg = ""
                with open('/dscdata/sendmsg', 'r+') as f:
                    for line in f:
                        msg = line.strip()
                if msg != "":
                    if "echo" in msg:
                        self.process_outbound_packet(self.MSG_TYPE_ECHO_REQ, msg[:200])
                    elif "1000" in msg:
                        for i in range(0, 1000):
                            self.event.wait(0.01)
                            self.process_outbound_packet(self.MSG_TYPE_MESSAGE, msg[:200])
                    elif "100" in msg:
                        for i in range(0, 100):
                            self.process_outbound_packet(self.MSG_TYPE_MESSAGE, msg[:200])
                    elif "10" in msg:
                        for i in range(0, 10):
                            self.process_outbound_packet(self.MSG_TYPE_MESSAGE, msg[:200])
                    else:
                        self.process_outbound_packet(self.MSG_TYPE_MESSAGE, msg[:200])
                    self.test_message_file.write("-----------------\n")
                    self.test_message_file.write(self.config.alias + " / [" + self.config.node_uuid + "]\n")
                    self.test_message_file.write(msg[:200] + "\n")
                os.remove('/dscdata/sendmsg')
                self.log.debug("Erased file.")

        except Exception:
            pass
