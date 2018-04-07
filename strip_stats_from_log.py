#!/usr/bin/python
import sys
from datetime import datetime

#2017-07-31 21:20:36,512| gps         | DEBUG   | lat long:41.5322646667N 72.645179W alt:58.2(M)
#2017-07-31 21:20:36,721| message     | DEBUG   | Beacon received. Alias: 'bbbb' RSSI:-4 SNR:6.0

#This is nasty, pay no mind. maybe I should format the logs better, or logs this data elsewhere(and in better form) for experiments
if len(sys.argv) > 1:
	beacon = ""
	with open(sys.argv[1],'r') as logfile:
		for line in logfile:
			if "Beacon received" in line:
				line_seg = line.split('|')
				timestamp = line_seg[0]

				beacon_data = line_seg[3].split('\'')
				alias = beacon_data[1]

				rf_data = beacon_data[2].split(' ')
				rssi = rf_data[1]
				snr = rf_data[2].strip()

				date = timestamp.split(' ')[0]
				time = timestamp.split(' ')[1].split(',')[0]

				datetime_obj = datetime.strptime(date +" "+time, '%Y-%m-%d %H:%M:%S')
				#print date,"|",time, "|",alias,"|",rssi,"|",snr
				beacon = [datetime_obj,alias.strip(),rssi,snr]

			elif "lat long" in line:
				line_seg = line.split('|')
				timestamp = line_seg[0]

				coords = line_seg[3].split(':')
				lat = coords[1].split(' ')[0]
				lon = coords[1].split(' ')[1]
				alt = coords[2].strip()
				date = timestamp.split(' ')[0]
				time = timestamp.split(' ')[1].split(',')[0]
				datetime_obj = datetime.strptime(date +" "+time, '%Y-%m-%d %H:%M:%S')
				if len(beacon) > 0:
					#print (datetime_obj - beacon[0]).total_seconds()
					if (datetime_obj - beacon[0]).total_seconds() <= 10 and 'dan' in beacon[1]:
						print beacon[1].strip() + "," + beacon[2] + "," +lat + "," + lon
						beacon = ""

