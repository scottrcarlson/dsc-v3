#!/usr/bin/env python
import time
from threading import *
import Queue
import hashlib
import logging
import struct
import binascii
import datetime

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

        self.alias = "midget01"
        self.group_key="eatme12345678900"
        self.network_key="eatme12345678901"

        self.network_plaintexts = []
        self.group_cleartexts = []

        self.config = config
        self.repeat_msg_list = []

        self.repeat_msg_index = 0

        self.msg_seg_list = []
        self.radio_inbound_queue = Queue.Queue() #Should we set a buffer size??
        self.radio_outbound_queue = Queue.Queue()
        self.radio_beacon_queue = Queue.Queue()

        self.crypto = crypto

        self.compose_msg = ""

        self.is_radio_tx = False

        self.log.info("Initialized Message Thread.")

    def run(self):
        tmda_frame_size = (self.config.tdma_total_slots * (self.config.tx_time + self.config.tx_deadband))

        self.event.wait(1)
        tick_ttl_reaper = 50
        cnt_ttl_reaper = 0
        while not self.event.is_set():
            try:
                packet = self.radio_inbound_queue.get_nowait()
            except Queue.Empty:
                pass
            else:
                #self.log.debug("Processing inbound packet.")
                self.process_packet(packet,'','')

            #Handle TTL, expiration
            if cnt_ttl_reaper > tick_ttl_reaper:
                #self.log.debug("Reaper gonna reap.")
                cnt_ttl_reaper = 0
                self.log.debug("Reap list size: %d " % (len(self.repeat_msg_list)))
                for network_cipher in self.repeat_msg_list:
                    network_plaintext = self.crypto.decrypt(self.network_key, str(network_cipher))
                    packet_sent_time = struct.unpack(">I",network_plaintext[:4])[0]
                    self.log.debug("Reap potential message 'sent time': %s" % (packet_sent_time))
                    packet_ttl = struct.unpack(">I",network_plaintext[4:8])[0]
                    self.log.debug("Reap potential message TTL: %s" % (packet_ttl))
                    if time.time() > packet_sent_time + packet_ttl:
                        self.log.debug("  Reap message.")
                        self.repeat_msg_list.remove(network_cipher)
                    
                        self.process_group_messages()
                        with self.radio_outbound_queue.mutex:
                            self.radio_outbound_queue.queue.clear()
                    else:
                        self.log.debug("  Reaper spared message.")
            else:
                cnt_ttl_reaper += 1

            self.fill_outbound_queue()
            self.event.wait(0.2)

    def stop(self):
        self.log.info( "Stopping Message Thread.")
        self.event.set()


    def fill_outbound_queue(self):
        if self.radio_outbound_queue.qsize() == 0:
            for msg in self.repeat_msg_list:
                self.radio_outbound_queue.put_nowait(msg)


    def process_composed_msg(self, msg):
        #DSCv3 Implement Message Encryption here

        #  Group Message Packet
        #  8 bytes msg author
        #  8 bytes spare
        #  208 bytes for Message
        #  Total 224 bytes group message Cipher


        author = 'RUSSET01'
        spare = "    " # 4 bytes
        group_cleartext = author+'DSC3'+spare+msg

        #self.log.debug("Spare size:     [" + str(len(spare)) + "]")
        #self.log.debug("author size:     " + str(len(author)))
        self.log.debug("Encrypting msg for /group/")
        group_cipher = self.crypto.encrypt(self.group_key,group_cleartext)
        #self.log.debug("group_cleartext: " + group_cleartext)
        #self.log.debug("group_cipher:     %s (%d)" % (binascii.hexlify(group_cipher), len(group_cipher)))
        #self.log.debug("group_cipher: " + group_cipher+ " size: " + str(len(group_cipher)))

        # Network Message Packet
        # 4 bytes for "sent-at" time in epoch
        # 4 bytes time to live iFpn seconds
        # 8 bytes spare
        # 224 byte group cipher
        # Total 240 bytes OTA mesage cipher
        timestamp = struct.pack(">I",time.time())
        ttl_sp = 30 # 2 minutes
        ttl = struct.pack(">I",ttl_sp)
        self.log.debug("Encrypting packet for /network/")
        ota_cipher = self.crypto.encrypt(self.network_key, timestamp+ttl+'DSC3'+'    '+group_cipher)
        #self.log.debug("ota_cipher: " + group_cipher + " size: " + str(len(ota_cipher)))
        self.log.debug("Adding this to repeat_msg_list: %s (%d)" % (binascii.hexlify(ota_cipher), len(ota_cipher)))
        self.repeat_msg_list.append(ota_cipher)

        return True # TODO Lets capture crypto error and report back false

    def add_msg_to_repeat_list(self,msg):
        if not self.check_for_dup(msg):
            self.repeat_msg_list.append(msg)
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

    def process_packet(self, msg, rf_rssi, rf_snr):
        self.log.debug("Processing Network Message.. ") #RSSI/SNR: " + rf_rssi + "/" + rf_snr)
        #self.log.debug("key:" + self.network_key + " size:" + str(len(self.network_key)))

        network_plaintext = self.crypto.decrypt(self.network_key, str(msg))
        #self.log.debug("network plaintext:" + binascii.hexlify(network_plaintext))

        #network_plaintext = network_plaintext[4:] # TODO: WTF
        """
        596a5929
        596a602c
        596a6073
        """

        if 'DSC3' in network_plaintext:

            #self.log.debug("check: %s (%d)" % (binascii.hexlify(network_plaintext), len(network_plaintext)))
            #print "network_plaintext: ", network_plaintext
            #print "len: ", len(network_plaintext)
            packet_sent_time = struct.unpack(">I",network_plaintext[:4])[0]  # unpack() always returns a tuple
            packet_ttl = struct.unpack(">I",network_plaintext[4:8])[0]  # unpack() always returns a tuple
            packet_mac = network_plaintext[8:12]
            packet_spare = network_plaintext[12:16]
            packet_group_cipher = network_plaintext[16:]
            #self.group_cipher.append(packet_group_cipher)
            #self.log.debug("Packet MAC:    " + packet_mac)
            #print type(packet_sent_time)
            #self.log.debug("Packet sent:   " + datetime.datetime.fromtimestamp(float(packet_sent_time)).strftime("%Y-%m-%d %H:%M:%S"))
            #self.log.debug("Packet TTL:    " +  str(packet_ttl) + " seconds")
            #self.log.debug("Packet Spare: [" + packet_spare + "]")
            #Add to Repeat Queue AS-IS
            if self.add_msg_to_repeat_list(msg):
                self.log.debug("Decrypting Group Message")
                group_cleartext = self.crypto.decrypt(self.group_key, packet_group_cipher)
                if 'DSC3' in group_cleartext:
                    packet_author = group_cleartext[:8]
                    packet_id = group_cleartext[8:12]
                    packet_spare = group_cleartext[12:16]
                    group_msg = group_cleartext[16:]
                    #print packet_author
                    #self.log.debug("Packet Author: " + packet_author)
                    #self.log.debug("Packet ID:     " + packet_id)
                    #self.log.debug("Packet Spare: [" + packet_spare + "]")
                    #self.log.debug("Group Msg:     " + group_msg)
                    if network_plaintext not in self.network_plaintexts:
                        print "********** APPEND TO NETWORK PLAINTEXT"
                        self.network_plaintexts.append(network_plaintext)
                        self.process_group_messages()
        else:
            self.log.debug("Packet Dropped due to missing MAC")

    def process_group_messages(self):
        self.group_cleartexts = []
        print "******************", len(self.network_plaintexts)
        for cipher in self.network_plaintexts:
            #print "cipher: ", cipher
            group_cleartext = self.crypto.decrypt(self.group_key, cipher[16:])
            print "!!!   ", group_cleartext
            packet_author = group_cleartext[:8]
            packet_id = group_cleartext[8:12]
            packet_spare = group_cleartext[12:16]
            group_msg = group_cleartext[16:]
            self.group_cleartexts.append(packet_author + ':' + group_msg)
        """
        self.log.debug("----------------- Beacon ------------------")
        self.log.debug( "Beacon Recv'd [" + friend + '] RSSI/SNR:[' + rf_rssi + ']/[' + rf_snr + ']')
        self.log.debug( "[" + friend + '] HASH:[' + beacon_hash + ']')
        self.lastseen_name = friend
        self.lastseen_rssi = rf_rssi
        self.lastseen_snr = rf_snr
        self.lastseen_time = time.time()
        """

        return True
