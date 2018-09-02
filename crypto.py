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
from base64 import b64encode
from os import urandom

BS = 16

pad = lambda s: s + (BS - len(s) % BS) * chr(BS - len(s) % BS)
unpad = lambda s : s[:-ord(s[len(s)-1:])]

#logging.basicConfig(level=logging.DEBUG,format='%(name)-12s| %(levelname)-8s| %(message)s')

class Crypto(object):
	def __init__(self):
		self.log = logging.getLogger()
		#self.log.setLevel(logging.DEBUG)

	def encrypt(self, key, pt):
		#self.log.debug("was asked to encrypt this plaintext (len: %d):  %s" % (len(pt), binascii.hexlify(pt)))

		#self.log.debug("key(%d): %s" %(len(key), key))
		key = pad(key)
		#self.log.debug("padded_key(%d): %s" %(len(key), binascii.hexlify(key)))
		#self.log.debug("iv(%d): %s" % (len(IV), binascii.hexlify(IV)))
		pt = pad(pt)
		#self.log.debug("padded_pt(%d): %s" % (len(pt), binascii.hexlify(pt)))
		iv = self.generateIV()
		cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
		encryptor = cipher.encryptor()
		ct = encryptor.update(pt) + encryptor.finalize()
		#self.log.debug("ct(%d): %s" % (len(ct), binascii.hexlify(ct)))
		return iv + ct

	def decrypt(self, key, ct):
		#self.log.debug("was asked to decrypt this ciphertext(len: %d): %s " % (len(ct), binascii.hexlify(ct)))
		#self.log.debug("key(%d): %s" %(len(key), binascii.hexlify(key)))	
		key = pad(key)
		#self.log.debug("padded_key(%d): %s" %(len(key), binascii.hexlify(key)))
		#self.log.debug("iv(%d): %s" % (len(IV), binascii.hexlify(IV)))

		iv = ct[:16]
		ct = ct[16:]
		cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
		decryptor = cipher.decryptor()
		pt = decryptor.update(ct) + decryptor.finalize()
		pt = unpad(pt)
		#self.log.debug("unpadded_pt(%d): (%s)" % (len(pt), binascii.hexlify(pt)))
		return pt

	def generateIV(self):
		random_bytes = urandom(16)
		return random_bytes

