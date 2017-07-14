#!/usr/bin/python
# ----------------------------
# --- GPS Helper Classes
#----------------------------

from threading import *
import time 
import serial
import pynmea2
import sys

GPS_SERIAL_DEVICE = '/dev/ttyUSB0'

def read(filename):
	f = open(filename)
	reader = pynmea2.NMEAStreamReader(f)
	while 1:
		for msg in reader.next():
			print(msg)

class Gps(Thread):
	def __init__(self):
		Thread.__init__(self)
		print "Initializing GPS Thread."
		self.stop_soon = False
		print " pynmea2 version:", pynmea2.__version__
	def start(self):
		print "Startings GPS Thread."
		com = None
		reader = pynmea2.NMEAStreamReader()

		if com is None:
			try:
				com = serial.Serial(GPS_SERIAL_DEVICE, timeout=5.0)
			except serial.SerialException:
				print('could not connect to %s' % filename)
				time.sleep(5.0)

		while not self.stop_soon:
			# TODO: handle exception thrown when out-of-sync
			data = com.read()
			for msg in reader.next(data):
				#print str(msg)
				parsed = pynmea2.parse(str(msg))
				try:
					if isinstance(parsed, pynmea2.types.talker.GGA):
						# print lat+lon that can be parsed by http://maps.google.com
						print "", str(parsed.latitude) + str(parsed.lat_dir), str(parsed.longitude).replace("-", "") + str(parsed.lon_dir)
				except:
					print "horse"
				time.sleep(4)

	def stop(self):
		print "Stopping GPS Thread."
		self.stop_soon = True
