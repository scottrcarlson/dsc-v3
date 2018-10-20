#!/usr/bin/python
from sh import btmgmt
import logging

log = logging.getLogger()


def init_ble():
    btmgmt.power.off()
    btmgmt.connectable.on()
    btmgmt.bondable.off()
    btmgmt.pairable.off()
    btmgmt.le.on()
    btmgmt.bredr.off()
    btmgmt.linksec.off()
    btmgmt.ssp.off()
    btmgmt.sc.on()
    btmgmt.privacy.off()  # would like to turn this on, need to test
    btmgmt.advertising.on()
    btmgmt.power.on()
    btmgmt.name("DSC0xbeef")
    btmgmt("io-cap", "0x04")  # DisplayKeyboard (for Numeric Comparison type pairing)
    log.debug("Initialized.")
    log.debug("interface: " + get_device_info()['interface'])
    log.debug("address: " + get_device_info()['address'])
    log.debug("settings: " + get_device_info()['settings'])
    log.debug("name: " + get_device_info()['name'])
    log.debug("alias: " + get_device_info()['alias'])


def get_device_info():
    info = btmgmt.info()
    info_lines = info.split("\n")

    results = {}
    results['interface'] = info_lines[1].split(':')[0]
    results['address'] = info_lines[2].split(' ')[1]
    results['settings'] = info_lines[4].split(':')[1]
    results['name'] = info_lines[5].split(' ')[1]
    results['alias'] = info_lines[6].split(' ')[1]
    return results