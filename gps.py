#!/usr/bin/python
# ----------------------------
# --- GPS Helper Classes
#----------------------------
from threading import *
import time 
import serial
import pynmea2
import sys
import logging

GPS_SERIAL_DEVICE = '/dev/ttyACM0'

class Gps(Thread):
	def __init__(self):
		Thread.__init__(self)
		self.event = Event()
		self.log = logging.getLogger()
		self.log.info("GPS Thread Started.")
		self.lat = ""
		self.long = ""

	def run(self):
		com = None
		reader = pynmea2.NMEAStreamReader()

		if com is None:
			try:
				com = serial.Serial(GPS_SERIAL_DEVICE, timeout=5.0)
			except serial.SerialException:
				self.log.warning("GPS Device not available.")
				time.sleep(5.0)

		while not self.event.is_set():
			# TODO: handle exception thrown when out-of-sync
			try:
				data = com.read()
				for msg in reader.next(data):
					#print str(msg)
					parsed = pynmea2.parse(str(msg))
					try:
						if isinstance(parsed, pynmea2.types.talker.GGA):
							# print lat+lon that can be parsed by http://maps.google.com
							self.lat = str(parsed.latitude) + str(parsed.lat_dir)
							self.long = str(parsed.longitude).replace("-", "") + str(parsed.lon_dir)
							self.log.debug(self.lat + " " + self.long)
					except Exception as e:
						self.log.error(str(e))
					time.sleep(1)
			except Exception as e:
				pass
				#self.log.error("GPS Read Error.")

	def stop(self):
		self.log.info( "Stopping GPS Thread.")
		self.event.set()

	def read(self,filename):
		f = open(filename)
		reader = pynmea2.NMEAStreamReader(f)
		while 1:
			for msg in reader.next():
				print(msg)