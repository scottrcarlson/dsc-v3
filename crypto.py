#!/usr/bin/env python
# ----------------------------
# --- Crypto Helper Class
# ----------------------------
import logging
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from os import urandom
import base64

BS = 16

pad = lambda s: s + (BS - len(s) % BS) * chr(BS - len(s) % BS)
unpad = lambda s : s[:-ord(s[len(s)-1:])]

# logging.basicConfig(level=logging.DEBUG,format='%(name)-12s| %(levelname)-8s| %(message)s')
class Crypto(object):
	def __init__(self):
		self.log = logging.getLogger()
		# self.log.setLevel(logging.DEBUG)

	def encrypt(self, key, pt):
		if isinstance(pt, unicode):
			ptbytestr = pt.encode('utf-8')
		else:
			ptbytestr = pt

		ptb64 = base64.encodestring(ptbytestr)
		key = pad(key)
		ptb64 = pad(ptb64)

		iv = self.generateIV()
		cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
		encryptor = cipher.encryptor()
		ct = encryptor.update(ptb64) + encryptor.finalize()

		return iv + ct

	def decrypt(self, key, ct):
		key = pad(key)
		iv = ct[:16]
		ct = ct[16:]
		cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
		decryptor = cipher.decryptor()
		ptb64 = decryptor.update(ct) + decryptor.finalize()
		ptb64 = unpad(ptb64)

		pt = base64.decodestring(ptb64)
		return pt

	def generateIV(self):
		random_bytes = urandom(16)
		return random_bytes

