#!/usr/bin/env python
import time
from threading import *
import Queue
import hashlib
import logging
import struct
import binascii

# OLD RE-WORK DOCUMENTION WHEN FINISHED WITH IMPLEMENATION
# Message thread is responsible for producing and consuming inbound/outbound radio packets via Queues.
# Perodically fill outbound queue with packets on the repeat list
# Process inbound queue to re-asemble packet segments into a complete message (3 matching segments)
#   Validate the cryptographic signature of the complete message, throw awawy message on verification failure.
#   If the signature is verified, add message to repeat list.
#       The message is further processed to:
#       extract beacons
#           Beacon signature verifies the sender
#           Beacon contains a MD5 hash of the sender's repeat list
#               The MD5 hashes are tracked via dictionary for all Nodes
#               If all hashes are equal, then everyone has everything.
#                   Confidence is increased while all hashes are equal
#                   if confidence is > some number, we will clear the repeat list
#                       and go into "quiet mode", which prevents all
#                       radio traffic except beacons for two tdma cycles
#                   Quiet Mode can also be initiated via a peer when:
#                       1. confidence > 1
#                       2?. All Hashes are equal except a node with quiet hash
#                       2?. All hashes are equal except a node with zero hash
#       OR
#       attempt to decrypt the message
#       if successful, then we know the message is for you.
class Message(Thread):
    def __init__(self, crypto, config):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger(self.__class__.__name__)
        #self.log.setLevel(logging.DEBUG)

        self.cleartext_msg_thread = {}
        self.msg_thread = {}
        self.repeat_msg_list = []

        self.repeat_msg_index = 0

        self.msg_seg_list = []
        self.radio_inbound_queue = Queue.Queue() #Should we set a buffer size??
        self.radio_outbound_queue = Queue.Queue()
        self.radio_beacon_queue = Queue.Queue()

        self.crypto = crypto

        self.compose_msg = ""

        self.is_radio_tx = False

        self.prev_msg_thread_size = {}
        self.log.info("Initialized Message Thread.")

    def run(self):
        tmda_frame_size = (self.config.tdma_total_slots * (self.config.tx_time + self.config.tx_deadband))
        #beacon_interval = tmda_frame_size
        #beacon_timeout = time.time()

        #self.build_friend_list();
        #seg_life_cnt = 0
        latchCheck = True

        self.event.wait(1)
        while not self.event.is_set():
            try:
                msg = self.radio_inbound_queue.get_nowait()
            except Queue.Empty:
                if not latchCheck:
                    latchCheck = True
                    self.check_for_complete_msgs()
            else:
                #print "Inbound Packet Processed."
                latchCheck = False
                self.add_msg_to_repeat_list(msg)
            timestamp = time.time()
            self.fill_outbound_queue()
            self.event.wait(0.05)

    def stop(self):
        self.log.info( "Stopping Message Thread.")
        self.event.set()

    def get_msg_thread(self,friend):
        #look up by alias to return the associate msg thread
        if friend in self.cleartext_msg_thread:
            return self.cleartext_msg_thread[friend]
        else:
            return None

    def decrypt_msg_thread(self, friend):
        #pass friends alias, and decrypt thread make available for viewing
        pass
"""
        if friend in self.msg_thread:

            if friend not in self.cleartext_msg_thread: #Initialize
                self.cleartext_msg_thread[friend] = []
            if friend not in self.prev_msg_thread_size: #Initialize
                self.prev_msg_thread_size[friend] = 0

                self.log.debug( "Decrypting Msg Thread for Viewing.")
            if len(self.msg_thread[friend]) != self.prev_msg_thread_size[friend]:
                self.prev_msg_thread_size[friend] = len(self.msg_thread[friend])
            #self.log.info( "Decrypting thread for viewing pleasure..."
                tmp_cleartext = []
                for cypher_msg in self.msg_thread[friend]:
                    try:
                        msg_arrived = float(cypher_msg.split('|',1)[0])
                        cypher_data = cypher_msg.split('|',1)[1]
                        clear_msg = self.crypto.decrypt_msg(cypher_data, self.config.alias)
                        clear_msg_segs = clear_msg.split('|')
                        msg_timestamp = time.mktime(time.strptime(clear_msg_segs[0], "%Y-%m-%d %H:%M:%S"))
                        tmp_cleartext.append(friend + " " + str(round(msg_arrived - msg_timestamp,0)) + "s")
                        #tmp_cleartext.append(clear_msg_segs[0]) # Timestamp
                        clear_text = clear_msg_segs[1]
                        while len(clear_text) > 20:
                            tmp_cleartext.append(clear_text[:20]) # Actual Msg
                            clear_text = clear_text[20:]
                        tmp_cleartext.append(clear_text)
                        del(clear_msg_segs) # ???
                        del(clear_msg) # del from mem, is this good enough. research
                    except Exception, e:
                        self.log.error( "Failed to decrypt: ", exc_info=True)
                self.log.debug( "Rebuilding Msg Thread: Complete.")
                self.cleartext_msg_thread[friend] = tmp_cleartext
        else:
            pass
            #print "Msg thread is empty:", friend
"""

    def fill_outbound_queue(self):
        if not self.quiet_mode:
            if self.radio_outbound_queue.qsize() == 0:
                for msg in self.repeat_msg_list:
                    self.radio_outbound_queue.put_nowait(msg)

    def generate_beacon(self):
        pass
        """
        if self.sig_auth: #Need sig_auth to sign beacons
            self.radio_beacon_queue.queue.clear()
            if self.quiet_mode:
                net_cmd = hashlib.md5(self.quiet_cmd).hexdigest()
                hash_repeat_list = self.last_repeat_hash
            else:
                net_cmd = hashlib.md5(self.normal_cmd).hexdigest()
                hash_repeat_list = hashlib.md5("".join(str(x) for x in sorted(self.repeat_msg_list))).hexdigest()
            beacon_msg = self.beacon_cmd + '|' + net_cmd + '|' + hash_repeat_list + '|' + str(len(self.repeat_msg_list))
            beacon_msg += ''.ljust(261 - len(beacon_msg)) #Needs to be 261 bytes total

            s_msg = self.crypto.sign_msg(beacon_msg, self.config.alias)
            beacon_msg += s_msg
            self.radio_beacon_queue.put_nowait(beacon_msg[:255])
            self.radio_beacon_queue.put_nowait(beacon_msg[255:510])
            seg1f = beacon_msg[:100]
            seg2f = beacon_msg[255:355]
            self.radio_beacon_queue.put_nowait(beacon_msg[510:] + seg1f + seg2f)
"""
    def process_composed_msg(self, msg):
        #DSCv3 Implement Message Encryption here

        #  Group Message Packet
        #  8 bytes msg author
        #  8 bytes spare
        #  208 bytes for Message
        #  Total 224 bytes group message Cipher
        timestamp = binascii.hexlify(struct.pack(">I",time.time()))
        ttl_sp = 120
        ttl = binascii.hexlify(struct.pack(">I",ttl_sp))

        # Network Message Packet
        # 4 bytes for time in epoch
        # 4 bytes time to live in seconds
        # 8 bytes spare
        # 224 byte group cipher
        # Total 240 bytes OTA mesage cipher
        #self.repeat_msg_list.append(ota_msg_cipher)



        #Need to enforce hard limit for cleartext
        #19 Bytes for timestamp (can save a few bytes with formatting)
        #214-19=195 msg size limit
        #Encrypt / Sign and add to the list
        #timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        #e_msg = self.crypto.encrypt_msg(timestamp+'|'+msg, friend)
        #s_msg = self.crypto.sign_msg(e_msg, self.config.alias)
        #self.repeat_msg_list.append(e_msg + s_msg)
        #total_msg = e_msg + s_msg
        #self.stats_max_repeat_size += 1
        #if len(self.repeat_msg_list) > self.stats_max_repeat_size:
        #    self.stats_max_repeat_size = len(self.repeat_msg_list)

        return True # TODO Lets capture keyczar error and report back false

    def add_msg_to_repeat_list(self,msg):
        if not self.check_for_dup(msg):
            self.repeat_msg_list.append(msg)
            if len(self.repeat_msg_list) > self.stats_max_repeat_size:
                self.stats_max_repeat_size = len(self.repeat_msg_list)
            return True
        else:
            self.log.debug( "Duplicate Message Received via Radio. Dropped")
            return False

    def check_for_dup(self,msg):
        #Check for duplicates in the repeat msg list, every encrypted msg is unique.
        for m in self.repeat_msg_list:
            #self.event.wait(0.1) #remove next time seen
            if msg == m:
                return True
        return False

    #def check_for_dup_msg_thread(self, msg, friend):
    #    if friend in self.msg_thread:
    #        for m in self.msg_thread[friend]:
    #            self.event.wait(0.1)
    #            if msg == m:
    #                return True
    #    return False

    def process_msg(self, msg, friend, rf_rssi, rf_snr):
        if self.beacon_cmd in msg:
            msg_data = msg.split('|')
            #cmd_hash = msg[len(self.beacon_cmd):(32 + len(self.beacon_cmd))]
            #beacon_hash = msg[(len(self.beacon_cmd) + 32):(64 + len(self.beacon_cmd))]
            cmd_hash = msg_data[1]
            beacon_hash = msg_data[2]
            msg_count = int(msg_data[3])
            if (msg_count > len(self.repeat_msg_list) and msg_count > self.stats_max_repeat_size):
                self.stats_max_repeat_size = msg_count
            elif len(self.repeat_msg_list) > self.stats_max_repeat_size:
                self.stats_max_repeat_size = len(self.repeat_msg_list)

            self.log.debug("----------------- Beacon ------------------")
            self.log.debug( "Beacon Recv'd [" + friend + '] RSSI/SNR:[' + rf_rssi + ']/[' + rf_snr + ']')
            self.log.debug( "[" + friend + '] HASH:[' + beacon_hash + ']')
            self.lastseen_name = friend
            self.lastseen_rssi = rf_rssi
            self.lastseen_snr = rf_snr
            self.lastseen_time = time.time()

            hash_repeat_list = hashlib.md5("".join(str(x) for x in sorted(self.repeat_msg_list))).hexdigest()
            self.beacon_quiet_hash[friend] = beacon_hash
            if not self.quiet_mode:
                if self.beacon_quiet_hash[friend] == hash_repeat_list and cmd_hash == hashlib.md5(self.quiet_cmd).hexdigest():
                    if hash_repeat_list != hashlib.md5('').hexdigest():
                        self.quiet_mode = True
                        self.network_equal = True
                        for node in self.beacon_quiet_confidence:
                            self.beacon_quiet_confidence[node] = 0
                        self.repeat_msg_list[:] = []
                        self.msg_seg_list[:] = []
                        self.last_repeat_hash = hash_repeat_list
                        self.log.debug( "Network Equal. Quiet Mode Activated by Peer.")
                elif self.beacon_quiet_hash[friend] == hash_repeat_list and hash_repeat_list != hashlib.md5('').hexdigest():
                    self.beacon_quiet_confidence[friend] += 1
                    self.log.debug( "Network Equal Confidence Increased with ["+friend+"]: " + str(self.beacon_quiet_confidence[friend]))
                    consensus = 0
                    for node in self.beacon_quiet_confidence:
                        if self.beacon_quiet_confidence[node] >= 1:
                            consensus += 1
                    if consensus == len(self.beacon_quiet_confidence):
                        self.quiet_mode = True
                        self.network_equal = True
                        for node in self.beacon_quiet_confidence:
                            self.beacon_quiet_confidence[node] = 0
                        self.repeat_msg_list[:] = []
                        self.msg_seg_list[:] = []
                        self.last_repeat_hash = hash_repeat_list
                        self.log.debug( "Network Equal. Quiet Mode Activated")
                elif self.beacon_quiet_hash[friend] != hash_repeat_list:
                    self.beacon_quiet_confidence[friend] = 0
                    if self.network_equal:
                        self.time_network_not_equal = time.time()
                    self.network_equal = False
                    self.log.debug( "Network NOT Equal. No Confidence with ["+friend+"]: " + str(self.beacon_quiet_confidence[friend]))

                elif hash_repeat_list == hashlib.md5('').hexdigest():
                    tally_empty = 0
                    for node in self.beacon_quiet_hash:
                        if self.beacon_quiet_hash[node] == hashlib.md5('').hexdigest():
                            tally_empty += 1
                    if tally_empty == len(self.beacon_quiet_hash):
                        self.network_equal = True
                        self.log.debug( "Network Equal [empty].")
            else:
                self.log.debug( "Network Equal. Quiet Mode Active.")
            self.log.debug( "Inbound Q/Seg List/Repeat List: " + '[' + str(self.radio_inbound_queue.qsize()) + ']/[' + str(len(self.msg_seg_list)) + ']/['+ str(len(self.repeat_msg_list))+']')
            return False
        else:
            return True
