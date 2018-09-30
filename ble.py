#!/usr/bin/python
import dbus
import dbus.service
import dbus.mainloop.glib
from sh import btmgmt
try:
    from gi.repository import GObject
except ImportError:
    import gobject as GObject
import signal
import logging
BUS_NAME = 'org.bluez'
AGENT_INTERFACE = 'org.bluez.Agent1'
AGENT_PATH = "/test/agent"

bus = None
device_obj = None
dev_path = None
mainloop = None
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
    btmgmt("io-cap","0x04") # DisplayKeyboard (for Numeric Comparison type pairing)
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


def ask(prompt):
    try:
        return raw_input(prompt)
    except Exception:
        return input(prompt)


def set_trusted(path):
    props = dbus.Interface(bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
    props.Set("org.bluez.Device1", "Trusted", True)


def dev_connect(path):
    dev = dbus.Interface(bus.get_object("org.bluez", path),
                            "org.bluez.Device1")
    dev.Connect()


class Rejected(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class Agent(dbus.service.Object):
    exit_on_release = True

    def set_exit_on_release(self, exit_on_release):
        self.exit_on_release = exit_on_release

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Release(self):
        log.debug("Release")
        if self.exit_on_release:
            mainloop.quit()

    @dbus.service.method(AGENT_INTERFACE, in_signature="ouq", out_signature="")
    def DisplayPasskey(self, device, passkey, entered):
        log.debug("DisplayPasskey (%s, %06u entered %u)" % (device, passkey, entered))

    @dbus.service.method(AGENT_INTERFACE, in_signature="ou", out_signature="")
    def RequestConfirmation(self, device, passkey):
        log.debug("RequestConfirmation (%s, %06d)" % (device, passkey))
        # log.debug(build_pair_req_msg(device, passkey))
        confirm = ask("Confirm passkey (yes/no): ")
        if (confirm == "yes"):
            pair_reply(device)
            return
        raise Rejected("Passkey doesn't match")

    @dbus.service.method(AGENT_INTERFACE, in_signature="", out_signature="")
    def Cancel(self):
        log.debug("Cancel")


def pair_reply(device):
    set_trusted(device)
    log.debug("Device paired")
    mainloop.quit()


def pair_error(error):
    err_name = error.get_dbus_name()
    if err_name == "org.freedesktop.DBus.Error.NoReply" and device_obj:
        log.debug("Timed out. Cancelling pairing")
        device_obj.CancelPairing()
    else:
        log.debug("Creating device failed: %s" % (error))
    mainloop.quit()


if __name__ == '__main__':
    log.debug("Active Pairing Agent")
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    init_ble()
    btmgmt.bondable.on()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    capability = "KeyboardDisplay"
    path = "/test/agent"
    # agent = Agent(bus, path)

    mainloop = GObject.MainLoop()
    obj = bus.get_object(BUS_NAME, "/org/bluez")
    manager = dbus.Interface(obj, "org.bluez.AgentManager1")
    manager.RegisterAgent(path, capability)
    manager.RequestDefaultAgent(path)
    log.debug("DSC BLE Pairing Agent Active.")
    log.debug("Waiting for a pair request")
    address = get_device_info()['address']
    log.debug("Bonded with: [" + address + "]")
    try:
        mainloop.run()
    except KeyboardInterrupt:
        pass
    btmgmt.bondable.off()

