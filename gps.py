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

# http://www.gpsinformation.org/dale/nmea.htm
#$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47
#Where:
#     GGA          Global Positioning System Fix Data
#     123519       Fix taken at 12:35:19 UTC
#     4807.038,N   Latitude 48 deg 07.038' N
#     01131.000,E  Longitude 11 deg 31.000' E
#     1            Fix quality: 0 = invalid
#                               1 = GPS fix (SPS)
#                               2 = DGPS fix
#                               3 = PPS fix
#			       4 = Real Time Kinematic
#			       5 = Float RTK
#                               6 = estimated (dead reckoning) (2.3 feature)
#			       7 = Manual input mode
#			       8 = Simulation mode
#     08           Number of satellites being tracked
#     0.9          Horizontal dilution of position
#     545.4,M      Altitude, Meters, above mean sea level
#     46.9,M       Height of geoid (mean sea level) above WGS84
#                      ellipsoid
#     (empty field) time in seconds since last DGPS update
#     (empty field) DGPS station ID number
#     *47          the checksum data, always begins with *

GPS_SERIAL_DEVICE = '/dev/ttyACM0'

class Gps(Thread):
	def __init__(self):
		Thread.__init__(self)
		self.event = Event()
		self.log = logging.getLogger()
		self.gps_enable = True # Expose to UI / Save Persistently
		self.gps_avail = True  # First Pass will set this correctly and log results once. 
		self.gps_quality = 0
		self.num_sats = 0
		self.gps_timestamp = 0
		self.lat = ""
		self.long = ""
		self.alt = ""
		self.log.info("GPS Thread Started.")

	def run(self):
		com = None
		reader = pynmea2.NMEAStreamReader()
		while not self.event.is_set():
			if self.gps_enable:
				if com is None:
					try:
						com = serial.Serial(GPS_SERIAL_DEVICE, timeout=5.0)
					except serial.SerialException:
						if self.gps_avail: # Falling Edge will Log Missing
							self.log.warning("GPS device missing")
						self.gps_avail = False
						time.sleep(15.0)
					else:
						self.log.warning("GPS device detected")
				else:
					try:
						data = com.read()
						for msg in reader.next(data):
							parsed = pynmea2.parse(str(msg))
							#print parsed
							try:
								if isinstance(parsed, pynmea2.types.talker.GGA):
									self.gps_quality = parsed.gps_qual
									self.num_sats = parsed.num_sats
									if self.gps_quality > 0 and self.gps_quality < 7:
										self.gps_avail = True
										self.log.debug("quality:" + str(self.gps_quality) + " #sats:" + str(self.num_sats))
										self.gps_timestamp = parsed.timestamp
										self.lat = str(parsed.latitude) + str(parsed.lat_dir)
										self.long = str(parsed.longitude).replace("-", "") + str(parsed.lon_dir)
										self.alt = str(parsed.altitude)
										self.alt_unit = str(parsed.altitude_units)
										self.log.debug("timestamp:" + str(self.gps_timestamp))
										
										# Need ZDA sentences! If we get date we can set our rtcs
										# my test unit does not spout ZDA by default, looking into this...

										# log lat+long that can be parsed by http://maps.google.com
										self.log.debug("lat long:" + self.lat + " " + self.long + " alt:" +
													   self.alt + "(" + self.alt_unit + ")")
							except Exception as e:
								self.gps_avail = False
								self.log.error(str(e))
					except Exception as e:
						# Force Reconnect 
						com = None
						self.gps_avail = False
						self.log.error("GPS device lost.")
			time.sleep(10)

	def stop(self):
		self.log.info("Stopping GPS Thread.")
		self.event.set()