#!/usr/bin/python
import dbus
import dbus.service
import dbus.mainloop.glib
import ble_gatt_base as gatt
import json
try:
    from gi.repository import GObject
except ImportError:
    import gobject as GObject
import logging
from threading import *
import traceback
import subprocess
import datetime
import Queue

DSC_SERVICE_UUID = 'deadbeef-0011-1001-1100-00000fffddd0'
DSC_SETTINGS_UUID = 'deadbeef-0011-1001-1100-00000fffddd1'
DSC_STATUS_UUID = 'deadbeef-0011-1001-1100-00000fffddd2'

DSC_MSG_INBOUND_UUID = 'deadbeef-0011-1001-1100-00000fffddda'
DSC_MSG_OUTBOUND_UUID = 'deadbeef-0011-1001-1100-00000fffdddb'
DSC_DATETIME_UUID = 'deadbeef-0011-1001-1100-00000fffdddc'

log = logging.getLogger()


class DscGatt(Thread):
    def __init__(self, quitdsc, message, config, radio):
        Thread.__init__(self)
        self.event = Event()
        self.log = logging.getLogger()
        self.log.info("DSC GATT Service Thread Started.")
        self.mainloop = None
        self.quitdsc = quitdsc
        self.config = config
        self.message = message
        self.radio = radio

    def run(self):
        global mainloop
        global service_manager
        # GObject.threads_init()
        # dbus.mainloop.glib.threads_init()
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

        bus = dbus.SystemBus()

        adapter = gatt.find_adapter(bus)
        if not adapter:
            log.debug('GattManager1 interface not found')
            return

        service_manager = dbus.Interface(
                bus.get_object(gatt.BLUEZ_SERVICE_NAME, adapter),
                gatt.GATT_MANAGER_IFACE)

        app = Application(bus, self.message, self.config, self.radio)

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
    def __init__(self, bus, message, config, radio):
        self.path = '/'
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        self.add_service(DSCService(bus, 0, message, config, radio))

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
    def __init__(self, bus, index, message, config, radio):
        gatt.Service.__init__(self, bus, index, DSC_SERVICE_UUID, True)
        self.add_characteristic(DSC_Settings_Characteristic(bus, 0, self, config))
        self.add_characteristic(DSC_Msg_Inbound_Characteristic(bus, 1, self, message))
        self.add_characteristic(DSC_Datetime_Characteristic(bus, 2, self))
        self.add_characteristic(DSC_Status_Characteristics(bus, 3, self, radio))
        self.add_characteristic(DSC_Msg_Outbound_Characteristic(bus, 4, self, message))


class DSC_Datetime_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_DATETIME_UUID,
                ['encrypt-authenticated-write'],
                service)
        self.value = 0
        self.notify_timer = None

    def WriteValue(self, value, options):
        try:
            GObject.source_remove(self.notify_timer)
        except Exception:
            pass
        log.debug("DSC Datetime: WriteValue Recvd")
        log.debug(repr(value))
        msg = ''
        # rawvalue = re.findall('\(([^)]+)', repr(value)[11:])
        for i in range(0, len(value) - 1):
            msg += chr(int(value[i]))
        log.debug(msg)
        self.value = value
        self.notify_timer = GObject.timeout_add(100, self.update_system_time)

    def update_system_time(self):
        try:
            GObject.source_remove(self.notify_timer)
        except Exception as e:
            logging.error(e, exc_info=True)
        epoch = ''
        for i in range(0, len(self.value) - 1):
            epoch += chr(int(self.value[i]))
        log.debug("System Time: " + str(datetime.datetime.now()))
        try:
            # I hate myself for using subprocess here, please better way?
            sudodate = subprocess.Popen(["sudo", "date", "-s", "@" + epoch])
            sudodate.communicate()
            # print sh.date(" ")
        except Exception as e:
            logging.error(e, exc_info=True)

        log.debug("New System Time: " + str(datetime.datetime.now()))
        return True


class DSC_Status_Characteristics(gatt.Characteristic):
    def __init__(self, bus, index, service, radio):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_STATUS_UUID,
                ['notify'],
                service)
        self.radio = radio
        self.notifying = False
        self.radio_state = ""
        self.radio_freq = ""
        self.system_time = ""

        self.value = self.PackageMsg()
   
        self.notify_timer = None

    def PackageMsg(self):
        result = self.BuildMsgPayload()
        try:
            new_value = []
            for c in result:
                new_value.append(ord(c))
        except Exception:
            log.error("DSC Package Message ERROR: PackeMsg")
        return new_value

    def BuildMsgPayload(self):
        payload = {}
        payload['rf_state'] = self.radio_state
        payload['rf_freq'] = self.radio_freq
        payload['time'] = self.system_time
        
        msg = {}
        msg['topic'] = "status"
        msg['payload'] = payload

        return json.dumps(msg, separators=(',', ':'))
        
    #   Notify Handset of Settings Change
    def notify_handset(self):
        try:
            outbound_data = self.radio.ble_handset_rf_status_queue.get_nowait()
            self.radio_freq, self.radio_state = outbound_data
        except Queue.Empty:
            self.radio_freq = ""
            self.radio_state = ""

        self.system_time = str(datetime.datetime.now())
        self.value = self.PackageMsg()
        value = []
        for ch in self.value:
            value.append(dbus.Byte(ch))
        self.PropertiesChanged(gatt.GATT_CHRC_IFACE, {'Value': value}, [])
        # log.debug("Sending Status Update to Handset")
        return self.notifying

    def StartNotify(self):
        log.debug('DSC Status Notification Enabled')
        if self.notifying:
            return
        else:
            # log.debug("Enabling")
            self.notify_timer = GObject.timeout_add(1000, self.notify_handset)
        self.notifying = True

    def StopNotify(self):
        log.debug('DSC Status Notification Disabled')
        if not self.notifying:
            return
        else:
            # log.debug("Disabling")
            try:
                GObject.source_remove(self.notify_timer)
            except Exception:
                pass
        self.notifying = False


class DSC_Msg_Inbound_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service, message):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_MSG_INBOUND_UUID,
                ['encrypt-authenticated-write', 'notify'],
                service)
        self.notifying = False
        self.message = message
        self.topic = ""
        self.msgcipher = ""
        self.msg = ""
        self.author = ""
        self.radio_uuid = ""
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
        try:
            new_value = []
            for c in result:
                new_value.append(ord(c))
        except Exception:
            log.error("DSC Package Message ERROR: PackageMsg")
        return new_value

    def BuildMsgPayload(self):
        payload = {}
        payload['msgcipher'] = self.msgcipher
        payload['msg'] = self.msg
        payload['author'] = self.author
        payload['uuid'] = self.radio_uuid
        payload['sent_time'] = self.sent_time
        payload['recv_time'] = self.recv_time
        payload['rssi'] = self.rssi
        payload['snr'] = self.snr
        payload['lat'] = self.gpslat
        payload['long'] = self.gpslong
        msg = {}
        msg['topic'] = self.topic
        msg['payload'] = payload

        return json.dumps(msg, separators=(',', ':'))

    def WriteValue(self, value, options):
        log.debug("DSC Inbound Msg: WriteValue Recvd")
        msg = ''
        rawvalue = re.findall('\(([^)]+)', repr(value)[11:])
        for i in range(0, len(rawvalue) - 1):
            msg += chr(int(rawvalue[i]))
        log.debug((msg))
        
    #   Notify Handset of Settings Change
    def notify_handset(self):
        try:
            outbound_data = self.message.ble_handset_msg_queue.get_nowait()
            self.author, self.radio_uuid, self.msg, self.msgcipher, self.sent_time, packet_ttl, msg_type, self.rssi, self.snr = outbound_data
            # log.debug("Sending Message: " + str(self.message.ble_handset_msg_queue.qsize()))
            if msg_type == self.message.MSG_TYPE_MESSAGE:
                self.topic = "newmsg"
            elif msg_type == self.message.MSG_TYPE_BEACON:
                self.topic = "newbeacon"
            # log.debug("Notify Handset Msg: " + self.author + ":" +
            #                                    self.radio_uuid + ":" +
            #                                    self.msg + ":" +
            #                                    str(self.sent_time) + ":" +
            #                                    str(packet_ttl) + ":" +
            #                                    topic + ":" +
            #                                    str(self.rssi) + ":" +
            #                                    str(self.snr))
            self.value = self.PackageMsg()
            value = []
            for ch in self.value:
                value.append(dbus.Byte(ch))
            self.PropertiesChanged(gatt.GATT_CHRC_IFACE, {'Value': value}, [])
            # log.debug("Sending handset message from queue")
        except Queue.Empty:
            pass
            # log.debug("No Messages")

        return self.notifying

    def StartNotify(self):
        log.debug("DSC Inbound Msg Notification Enabled")
        if self.notifying:
            return
        else:
            pass
            self.notify_timer = GObject.timeout_add(1000, self.notify_handset)
        self.notifying = True

    def StopNotify(self):
        if not self.notifying:
            log.debug("DSC Inbound Msg Notification Disabled")
            return
        else:
            try:
                GObject.source_remove(self.notify_timer)
            except Exception:
                pass
        self.notifying = False


class DSC_Msg_Outbound_Characteristic(gatt.Characteristic):
    def __init__(self, bus, index, service, message):
        gatt.Characteristic.__init__(
                self, bus, index,
                DSC_MSG_OUTBOUND_UUID,
                ['encrypt-authenticated-write'],
                service)
        self.timer = None
        self.message = message
        self.value = ""

    def WriteValue(self, value, options):
        msg = ''
        for i in range(0, len(value)):
            msg += chr(int(value[i]))
        log.debug(msg)
        try:
            parms = json.loads(msg)
            if (parms['topic'] == 'sendmsg'):
                self.config_timer = GObject.timeout_add(100, self.sendMsg)
                self.value = parms['msg'] + "," + parms['author']
                
        except Exception:
            log.error("Outbound Msg Write Error")

    def sendMsg(self):
        print self.value
        if "echo" in self.value.split(",")[0]:
            self.message.process_outbound_packet(self.message.MSG_TYPE_ECHO_REQ, self.value.split(",")[0])
        else:
            self.message.process_outbound_packet(self.message.MSG_TYPE_MESSAGE, self.value.split(",")[0])


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
        try:
            new_value = []
            for c in result:
                new_value.append(ord(c))
        except Exception:
            print "DSC getparms ERROR: " + traceback.format.exc()
        return new_value

    def ReadValue(self, options):
        print "getparms msg received."
        # print (options)
        return self.value

    def WriteValue(self, value, options):
        try:
            GObject.source_remove(self.notify_timer)
        except Exception:
            pass

        try:
            GObject.source_remove(self.save_timer)
        except Exception:
            pass
        log.debug("setparms msg received.")
        # log.debug(repr(value))
        msg = ''
        for i in range(0, len(value)):
            # print repr(value[i])
            msg += chr(int(value[i]))
        log.debug(msg)
        try:
            parms = json.loads(msg)
            # print (parms)
            # print "Topic:" + parms['topic']
            if (parms['topic'] == 'setparms'):
                self.parms = parms
                self.config_timer = GObject.timeout_add(1000, self._dsc_set_params)
                # self._dsc_set_params(parms)

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
            payload['alias'] = self.config.alias
            payload['netkey'] = self.config.netkey
            payload['groupkey'] = self.config.groupkey
            payload['registered'] = self.config.registered

            msg = {}
            msg['topic'] = "getparms"
            msg['payload'] = payload
        except Exception:
            log.error("Error Getting Config Settings")
        return json.dumps(msg, separators=(',', ':'))

    def _dsc_set_params(self):
        try:
            GObject.source_remove(self.config_timer)
        except Exception:
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
            self.config.set_coding_rate(parms['coding_rate'] + 1)
            self.config.set_tx_time(parms['tx_time'])
            self.config.set_tx_power(parms['tx_power'])
            self.config.set_sync_word(parms['sync_word'])
            self.config.set_alias(parms['alias'].encode("ascii"))
            self.config.set_netkey(parms['netkey'].encode("ascii"))
            self.config.set_groupkey(parms['groupkey'].encode("ascii"))
            self.config.set_registered(parms['registered'])
        except Exception:
            traceback.print_exc()
            log.error("Failed to Set Config Params")
        if self.notifying:
            self.notify_timer = GObject.timeout_add(6000, self.notify_handset)
        self.value = self.PackageSettings()

    def _persist_settings(self):
        self.config.save_config(True)

    #   Notify Handset of Settings Change
    def notify_handset(self):
        GObject.source_remove(self.notify_timer)
        if self.config.req_save_config:
            self.config.req_save_config = False
            self.save_timer = GObject.timeout_add(10000, self._persist_settings)
        log.debug("Notifying Handset of Settings Change")
        value = []
        for ch in self.value:
            value.append(dbus.Byte(ch))
        self.PropertiesChanged(gatt.GATT_CHRC_IFACE, {'Value': value}, [])
        return self.notifying

    def _check_for_notifications(self):
        print 'Checking Settings notifications'
        if not self.notifying:
            return
        GObject.timeout_add(1000, self.notify_handset)

    def StartNotify(self):
        log.debug('DSC Settings Notification Enabled')
        if self.notifying:
            return
        self.notifying = True
        return True

    def StopNotify(self):
        log.debug('DSC Settings Notification Disabled')
        if not self.notifying:
            return
        self.notifying = False


def register_app_cb():
    log.debug('DSC GATT Services Registered.')


def register_app_error_cb(error):
    log.debug('Failed to register application: ' + str(error))
    mainloop.quit()
