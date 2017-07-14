#!/usr/bin/env python
# ----------------------------
# --- Crypto Helper Class
#----------------------------
import os, binascii, sys, datetime
import shutil
import time
from config import Config
import logging
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

IV = 'A' * 16 # TODO: fixme
BS = 16

pad = lambda s: s + (BS - len(s) % BS) * chr(BS - len(s) % BS) 
unpad = lambda s : s[:-ord(s[len(s)-1:])]

logging.basicConfig(level=logging.DEBUG,format='%(name)-12s| %(levelname)-8s| %(message)s')

class Crypto(object):
	def __init__(self):
		self.log = logging.getLogger(self.__class__.__name__)
		self.NETWORK_KEY = "mykey" # TODO: take input from keypad
		self.GROUP_KEY = "mykey2"  # TODO: take input from keypad
		self.log.setLevel(logging.DEBUG)

	def encrypt(self, key, pt):
		self.log.debug("key(%d): %s" %(len(key), binascii.hexlify(key)))
		key = pad(key)
		self.log.debug("padded_key(%d): %s" %(len(key), binascii.hexlify(key)))
		self.log.debug("iv(%d): %s" % (len(IV), binascii.hexlify(IV)))
		self.log.debug("pt(%d): %s" % (len(pt), binascii.hexlify(pt)))
		pt = pad(pt)
		self.log.debug("padded_pt(%d): %s" % (len(pt), binascii.hexlify(pt)))
		cipher = Cipher(algorithms.AES(key), modes.CBC(IV), backend=default_backend())
		encryptor = cipher.encryptor()
		ct = encryptor.update(pt) + encryptor.finalize()
		self.log.debug("ct(%d): %s" % (len(ct), binascii.hexlify(ct)))
		return ct

	def decrypt(self, key, ct):
		self.log.debug("key(%d): %s" %(len(key), binascii.hexlify(key)))
		key = pad(key)
		self.log.debug("padded_key(%d): %s" %(len(key), binascii.hexlify(key)))
		self.log.debug("iv(%d): %s" % (len(IV), binascii.hexlify(IV)))
		cipher = Cipher(algorithms.AES(key), modes.CBC(IV), backend=default_backend())
		decryptor = cipher.decryptor()
		pt = decryptor.update(ct) + decryptor.finalize()
		pt = unpad(pt)
		self.log.debug("unpadded_pt(%d): %s" % (len(pt), binascii.hexlify(pt)))

if __name__ == "__main__":
	c = Crypto()
	ct = c.encrypt(c.NETWORK_KEY, "mymsg\x41")
	c.decrypt(c.NETWORK_KEY, ct)
	
	c = Crypto()
	ct = c.encrypt(c.GROUP_KEY, "mymsg\x41")
	c.decrypt(c.GROUP_KEY, ct)


