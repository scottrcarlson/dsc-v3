#!/usr/bin/python
import dbus
import dbus.service
import dbus.mainloop.glib
import ble_gatt_base as gatt
import sh
import json
import sys
try:
  from gi.repository import GObject
except ImportError:
  import gobject as GObject
import signal
import sys
import logging
from threading import *
import traceback
import subprocess
import datetime

DSC_SERVICE_UUID = 'deadbeef-0011-1001-1100-00000fffddd0'
DSC_SETTINGS_UUID = 'deadbeef-0011-1001-1100-00000fffddd1'
DSC_NOTIFY_UUID = 'deadbeef-0011-1001-1100-00000fffddd3'

DSC_MSG_INBOUND_UUID = 'deadbeef-0011-1001-1100-00000fffddda'
DSC_MSG_OUTBOUND_UUID = 'deadbeef-0011-1001-1100-00000fffdddb'
DSC_DATETIME_UUID = 'deadbeef-0011-1001-1100-00000fffdddc'

log = logging.getLogger()

class DscGatt(Thread):
    def __init__(self, quitdsc, config):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()
        self.log.info("DSC GATT Service Thread Started.")
        self.mainloop = None
        self.quitdsc = quitdsc
        self.config = config

    def run(self):
        global mainloop
        global service_manager
        #GObject.threads_init()
        #dbus.mainloop.glib.threads_init()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        bus = dbus.SystemBus()

        adapter = gatt.find_adapter(bus)
        if not adapter:
            log.debug('GattManager1 interface not found')
            return

        service_manager = dbus.Interface(
                bus.get_object(gatt.BLUEZ_SERVICE_NAME, adapter),
                gatt.GATT_MANAGER_IFACE)

        app = Application(bus, self.config)

        self.mainloop = GObject.MainLoop()

        self.log.debug('Registering DSC GATT application...')

        service_manager.RegisterApplication(app.get_path(), {},
                                        reply_handler=register_app_cb,
                                        error_handler=register_app_error_cb)
        try:
            self.mainloop.run()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        self.log.info("Stopping DSC GATT Service Thread.")
        self.mainloop.quit()
        self.quitdsc()
        self.event.set()

class Application(dbus.service.Object):
    """
    org.bluez.GattApplication1 interface implementation
    """
    def __init__(self, bus, config):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(DSCService(bus, 0, config))

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(gatt.DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        response = {}

        for service in self.services:
            response[service.get_path()] = service.get_properties()
            chrcs = service.get_characteristics()
            for chrc in chrcs:
                response[chrc.get_path()] = chrc.get_properties()
                descs = chrc.get_descriptors()
                for desc in descs:
                    response[desc.get_path()] = desc.get_properties()

        return response

class DSCService(gatt.Service):
    def __init__(self, bus, index, config):
        gatt.Service.__init__(self, bus, index, DSC_SERVICE_UUID, True)
        self.add_characteristic(DSC_Settings_Characteristic(bus, 0, self, config))
        self.add_characteristic(DSC_Msg_Inbound_Characteristic(bus, 1, self))
        self.add_characteristic(DSC_Datetime_Characteristic(bus, 2, self))

class DSC_Datetime_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_DATETIME_UUID,
                ['encrypt-authenticated-write', 'notify'],
                service)
        self.notifying = False
        self.value = 0
        self.notify_timer = None

    def WriteValue(self, value, options):
        try:
            GObject.source_remove(self.notify_timer)
        except:
            pass
        log.debug("DSC Datetime: WriteValue Recvd")
        log.debug(repr(value))
        msg = ''
        #rawvalue = re.findall('\(([^)]+)', repr(value)[11:])
        for i in range(0,len(value)-1):
            msg += chr(int(value[i]))
        log.debug(msg)
        self.value = value
        if self.notifying:
            self.notify_timer = GObject.timeout_add(100, self.notify_handset)

    ### Notify Handset of Settings Change
    def notify_handset(self):
        try:
            GObject.source_remove(self.notify_timer)
        except Exception as e:
            logging.error(e, exc_info=True)   
        epoch = ''
        for i in range(0,len(self.value)-1):
            epoch += chr(int(self.value[i]))
        log.debug("System Time: " + str(datetime.datetime.now()))
        log.debug("Changing System Time: " + epoch)
        datearg = "'@" + epoch + "'"
        try:
            #I hate myself for using subprocess here, please better way?
            sudodate = subprocess.Popen(["sudo", "date", "-s", "@" + epoch])
            sudodate.communicate()
            #print sh.date(" ")
        except Exception as e:
            logging.error(e, exc_info=True)

        #log.debug("DSC System Time: " + )
        log.debug("Notifying Handset of Datetime Change")
        log.debug("New System Time: " + str(datetime.datetime.now()))
        #value = []
        #for ch in self.value:
        #    value.append(dbus.Byte(ch))
        #self.PropertiesChanged(gatt.GATT_CHRC_IFACE, { 'Value': value }, [])
        return self.notifying

    def StartNotify(self):
        log.debug('DSC Datetime Notification Enabled')
        if self.notifying:
            log.debug('Already notifying, nothing to do')
            return

        self.notifying = True

    def StopNotify(self):
        log.debug('DSC Datetime Notification Disabled')
        if not self.notifying:
            log.debug('Not notifying, nothing to do')
            return
        self.notifying = False

class DSC_Msg_Inbound_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_MSG_INBOUND_UUID,
                ['encrypt-authenticated-write', 'notify'],
                service)
        self.notifying = False

        self.msg = "Hello, is there anybody out there?"
        self.author = "Someone"
        self.recv_time = 0
        self.sent_time = 0
        self.rssi = -120  
        self.snr = 2
        self.gpslat = 0
        self.gpslong = 0
        self.value = self.PackageMsg()

        self.notify_timer = None

    def PackageMsg(self):
        result = self.BuildMsgPayload()
        try :
            new_value = []
            for c in result:
                new_value.append(ord(c))
        except Exception as e:
            log.error("DSC Package Message ERROR: PackeMsg")
        return new_value

    def BuildMsgPayload(self):
        payload = {}
        payload['msg'] = self.msg
        payload['author'] = self.author
        payload['sent_time'] = self.sent_time
        payload['recv_time'] = self.recv_time   
        payload['rssi'] = self.rssi
        payload['snr'] = self.snr
        payload['lat'] = self.gpslat
        payload['long'] = self.gpslong

        msg = {}
        msg['topic'] = "newmsg"
        msg['payload'] = payload

        return json.dumps(msg,separators=(',',':'))

    def WriteValue(self, value, options):
        log.debug("DSC Inbound Msg: WriteValue Recvd")
        msg = ''
        rawvalue = re.findall('\(([^)]+)', repr(value)[11:])
        for i in range(0,len(rawvalue)-1):
            msg += chr(int(rawvalue[i]))
        log.debug((msg))
        self.notify_timer = GObject.timeout_add(1000, self.notify_handset)

    ### Notify Handset of Settings Change
    def notify_handset(self):
        log.debug("Notifying Handset of Settings Change")
        try:
            GObject.source_remove(self.notify_timer)
        except Exception as e:
            pass
        value = []
        for ch in self.value:
            value.append(dbus.Byte(ch))
        self.PropertiesChanged(gatt.GATT_CHRC_IFACE, { 'Value': value }, [])
        return self.notifying

    def StartNotify(self):
        log.debug('DSC Inbound Msg Notification Enabled')
        if self.notifying:
            log.debug('Already notifying, nothing to do')
            return
        #else:
            #self.notify_timer = GObject.timeout_add(30000, self.notify_handset)
        self.notifying = True

    def StopNotify(self):
        log.debug('Notification Stop command recvd')
        if not self.notifying:
            log.debug('Not notifying, nothing to do')
            return
        #else:
            #try:
            #    GObject.source_remove(self.notify_timer)
            #except Exception as e:
            #    pass
        self.notifying = False

class DSC_Settings_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service, config):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_SETTINGS_UUID,
                ['encrypt-authenticated-read', 'encrypt-authenticated-write', 'notify'],
                service)
        self.notifying = False
        self.config = config
        self.value = self.PackageSettings()
        self.notify_timer = None
        self.config_timer = None
        self.save_timer = None
        self.parms = None

    def PackageSettings(self):
        result = self._dsc_get_params()
        try :
            new_value = []
            for c in result:
                new_value.append(ord(c))
        except Exception as e:
            print  "DSC getparms ERROR: " + traceback.format.exc()   
        return new_value      

    def ReadValue(self, options):
        print "getparms msg received."
        print (options)
        return self.value

    def WriteValue(self, value, options):
        try:
            GObject.source_remove(self.notify_timer)
        except:
            pass

        try:
            GObject.source_remove(self.save_timer)
        except:
            pass    
        log.debug("setparms msg received.")
        #log.debug(repr(value))
        msg = ''
        for i in range(0,len(value)):
            #print repr(value[i])
            msg += chr(int(value[i]))
        log.debug(msg)
        try:
            parms = json.loads(msg)
            print (parms)
            print "Topic:" + parms['topic']
            if (parms['topic'] == 'setparms'):
                self.parms = parms
                self.config_timer = GObject.timeout_add(1000, self._dsc_set_params)
                #self._dsc_set_params(parms)

        except Exception:
            traceback.print_exc()

        self.value = self.PackageSettings()

    def _dsc_get_params(self):
        try:
            payload = {}
            payload['airplane_mode'] = self.config.airplane_mode
            payload['total_nodes'] = self.config.tdma_total_slots
            payload['tdma_slot'] = self.config.tdma_slot
            payload['tx_time'] = self.config.tx_time
            payload['deadband'] = self.config.tx_deadband
            payload['freq'] = self.config.freq
            payload['bw'] = self.config.bandwidth
            payload['sp_factor'] = self.config.spread_factor
            payload['coding_rate'] = self.config.coding_rate
            payload['tx_power'] = self.config.tx_power
            payload['sync_word'] = self.config.sync_word

            msg = {}
            msg['topic'] = "getparms"
            msg['payload'] = payload
        except Exception:
            log.error("Error Getting Config Settings")
        return json.dumps(msg,separators=(',',':'))

    def _dsc_set_params(self):
        try:
            GObject.source_remove(self.config_timer)
        except:
            pass
        try:
            parms = self.parms
            self.config.set_airplane_mode(parms['airplane_mode'])
            self.config.set_tdma_total_slots(parms['total_nodes'])
            self.config.set_tdma_slot(parms['tdma_slot'])
            self.config.set_tx_deadband(parms['deadband'])
            self.config.set_freq(parms['freq'])
            self.config.set_bandwidth(parms['bw'])
            self.config.set_spread_factor(parms['sp_factor'])
            self.config.set_coding_rate(parms['coding_rate'])
            self.config.set_tx_time(parms['tx_time'])
            self.config.set_tx_power(parms['tx_power'])
            self.config.set_sync_word(parms['sync_word'])
        except Exception:
            traceback.print_exc()
            log.error("Failed to Set Config Params")
        if self.notifying:
            self.notify_timer = GObject.timeout_add(6000, self.notify_handset)
        self.value = self.PackageSettings()

    def _persist_settings(self):
        self.config.save_config(True)

    ### Notify Handset of Settings Change
    def notify_handset(self):
        GObject.source_remove(self.notify_timer)
        if self.config.req_save_config:
            self.config.req_save_config = False
            self.save_timer = GObject.timeout_add(10000, self._persist_settings)
        print "Notifying Handset of Settings Change"
        value = []
        for ch in self.value:
            value.append(dbus.Byte(ch))
        self.PropertiesChanged(gatt.GATT_CHRC_IFACE, { 'Value': value }, [])
        return self.notifying

    def _check_for_notifications(self):
        print 'Checking Settings notifications'
        if not self.notifying:
            return
        GObject.timeout_add(1000, self.notify_handset)

    def StartNotify(self):
        print 'DSC Settings Notification Enabled'
        if self.notifying:
            print 'Already notifying, nothing to do'
            return
        self.notifying = True
        return True

    def StopNotify(self):
        if not self.notifying:
            print 'Not notifying, nothing to do'
            return
        self.notifying = False

def register_app_cb():
    log.debug('DSC GATT Services Registered.')

def register_app_error_cb(error):
    log.debug('Failed to register application: ' + str(error))
    mainloop.quit()