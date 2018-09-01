#!/usr/bin/python

from sh import btmgmt
import json
import dbus
import dbus.service
import dbus.mainloop.glib
try:
  from gi.repository import GObject
except ImportError:
  import gobject as GObject
import signal
import sys

BUS_NAME = 'org.bluez'
AGENT_INTERFACE = 'org.bluez.Agent1'
AGENT_PATH = "/test/agent"

bus = None
device_obj = None
dev_path = None
mainloop = None

CMD_INIT = "init"
CMD_ADVERTISE_ON = "advertise_on"
CMD_ADVERTISE_OFF = "advertise_off"
CMD_PAIRING_ON = "pairing_on"
CMD_PAIRING_OFF = "pairing_off"
CMD_CLEAR_DEVICES = "clear_devices"
CMD_PAIR_ACCEPT = "pair_accept"
CMD_PAIR_REJECT = "pair_reject"

def build_pair_req_msg(addr, passkey):
	msg = {}
	msg['addr'] = addr
	msg['passkey'] = passkey
	return json.dumps(msg)

def init_dsc_ble():
	btmgmt.power.off()
	btmgmt.connectable.on()
	btmgmt.bondable.on()
	btmgmt.pairable.on()
	btmgmt.le.on()
	btmgmt.bredr.off()
	btmgmt.linksec.off()
	btmgmt.ssp.off()
	btmgmt.sc.on()
	btmgmt.privacy.off()
	btmgmt.advertising.on()

	btmgmt("io-cap","0x04") #DisplayKeyboard (for Numeric Comparison type pairing)
	btmgmt.power.on()

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
	except:
		return input(prompt)

def set_trusted(path):
	props = dbus.Interface(bus.get_object("org.bluez", path),
					"org.freedesktop.DBus.Properties")
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

	@dbus.service.method(AGENT_INTERFACE,
					in_signature="", out_signature="")
	def Release(self):
		print("Release")
		if self.exit_on_release:
			mainloop.quit()

	@dbus.service.method(AGENT_INTERFACE, in_signature="os", out_signature="")
	def AuthorizeService(self, device, uuid):
		print("AuthorizeService (%s, %s)" % (device, uuid))
		authorize = ask("Authorize connection (yes/no): ")
		if (authorize == "yes"):
			return
		raise Rejected("Connection rejected by user")

	@dbus.service.method(AGENT_INTERFACE,
                                    in_signature="o", out_signature="s")
	def RequestPinCode(self, device):
		print("RequestPinCode (%s)" % (device))
		set_trusted(device)
		return ask("Enter PIN Code: ")

	@dbus.service.method(AGENT_INTERFACE,
                                    in_signature="o", out_signature="u")
	def RequestPasskey(self, device):
		print("RequestPasskey (%s)" % (device))
		set_trusted(device)
		passkey = ask("Enter passkey: ")
		return dbus.UInt32(passkey)

	@dbus.service.method(AGENT_INTERFACE,
					in_signature="ouq", out_signature="")
	def DisplayPasskey(self, device, passkey, entered):
		print("DisplayPasskey (%s, %06u entered %u)" %
						(device, passkey, entered))

	@dbus.service.method(AGENT_INTERFACE,
                                    in_signature="os", out_signature="")
	def DisplayPinCode(self, device, pincode):
		print("DisplayPinCode (%s, %s)" % (device, pincode))

	@dbus.service.method(AGENT_INTERFACE,
					in_signature="ou", out_signature="")
	def RequestConfirmation(self, device, passkey):
		print("RequestConfirmation (%s, %06d)" % (device, passkey))
		print build_pair_req_msg(device, passkey)
		confirm = ask("Confirm passkey (yes/no): ")
		if (confirm == "yes"):
			pair_reply(device)
			return
		raise Rejected("Passkey doesn't match")

	@dbus.service.method(AGENT_INTERFACE,
                                    in_signature="o", out_signature="")
	def RequestAuthorization(self, device):
		print("RequestAuthorization (%s)" % (device))
		auth = ask("Authorize? (yes/no): ")
		if (auth == "yes"):
			return
		raise Rejected("Pairing rejected")


	@dbus.service.method(AGENT_INTERFACE,
					in_signature="", out_signature="")
	def Cancel(self):
		print("Cancel")





def pair_reply(device):
	set_trusted(device)
	print("Device paired")
	mainloop.quit()

def pair_error(error):
	err_name = error.get_dbus_name()
	if err_name == "org.freedesktop.DBus.Error.NoReply" and device_obj:
		print("Timed out. Cancelling pairing")
		device_obj.CancelPairing()
	else:
		print("Creating device failed: %s" % (error))
	mainloop.quit()


if __name__ == '__main__':
	signal.signal(signal.SIGINT, signal.SIG_DFL)

	dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
	bus = dbus.SystemBus()

	capability = "KeyboardDisplay"
	path = "/test/agent"
	agent = Agent(bus, path)

	mainloop = GObject.MainLoop()
	obj = bus.get_object(BUS_NAME, "/org/bluez");
	manager = dbus.Interface(obj, "org.bluez.AgentManager1")
	manager.RegisterAgent(path, capability)
	manager.RequestDefaultAgent(path)
	print("DSC BLE Pairing Agent Active.")

	init_dsc_ble()
	print("DSC BLE Interface Configured and Active.")
	print get_device_info()
	address = get_device_info()['address']
	print("DSC MAC: [" + address + "]")
	print("Waiting for pair request...")
	try:
		mainloop.run()
	except KeyboardInterrupt:
		btmgmt.bondable.off()

	print("Exit. DSC is not Bondable.")
	#btmgmt.bondable.off()


"""
btmgmt available commands
config                                            Show configuration info
info                                              Show controller info
extinfo                                           Show extended controller info
auto-power                                        Power all available features
power <on/off>                                    Toggle powered state
discov <yes/no/limited> [timeout]                 Toggle discoverable state
connectable <on/off>                              Toggle connectable state
fast-conn <on/off>                                Toggle fast connectable state
bondable <on/off>                                 Toggle bondable state
pairable <on/off>                                 Toggle bondable state
linksec <on/off>                                  Toggle link level security
ssp <on/off>                                      Toggle SSP mode
sc <on/off/only>                                  Toogle SC support
hs <on/off>                                       Toggle HS support
le <on/off>                                       Toggle LE support
advertising <on/off>                              Toggle LE advertising
bredr <on/off>                                    Toggle BR/EDR support
privacy <on/off>                                  Toggle privacy support
class <major> <minor>                             Set device major/minor class
disconnect [-t type] <remote address>             Disconnect device
con                                               List connections
find [-l|-b] [-L]                                 Discover nearby devices
find-service [-u UUID] [-r RSSI_Threshold] [-l|-b] Discover nearby service
stop-find [-l|-b]                                 Stop discovery
name <name> [shortname]                           Set local name
pair [-c cap] [-t type] <remote address>          Pair with a remote device
cancelpair [-t type] <remote address>             Cancel pairing
unpair [-t type] <remote address>                 Unpair device
keys                                              Load Link Keys
ltks                                              Load Long Term Keys
irks [--local <index>] [--file <file path>]       Load Identity Resolving Keys
block [-t type] <remote address>                  Block Device
unblock [-t type] <remote address>                Unblock Device
add-uuid <UUID> <service class hint>              Add UUID
rm-uuid <UUID>                                    Remove UUID
clr-uuids                                         Clear UUIDs
local-oob                                         Local OOB data
remote-oob [-t <addr_type>] [-r <rand192>] [-h <hash192>] [-R <rand256>] [-H <hash256>] <addr> Remote OOB data
did <source>:<vendor>:<product>:<version>         Set Device ID
static-addr <address>                             Set static address
public-addr <address>                             Set public address
ext-config <on/off>                               External configuration
debug-keys <on/off>                               Toogle debug keys
conn-info [-t type] <remote address>              Get connection information
io-cap <cap>                                      Set IO Capability
scan-params <interval> <window>                   Set Scan Parameters
get-clock [address]                               Get Clock Information
add-device [-a action] [-t type] <address>        Add Device
del-device [-t type] <address>                    Remove Device
clr-devices                                       Clear Devices
bredr-oob                                         Local OOB data (BR/EDR)
le-oob                                            Local OOB data (LE)
advinfo                                           Show advertising features
advsize [options] <instance_id>                   Show advertising size info
add-adv [options] <instance_id>                   Add advertising instance
rm-adv <instance_id>                              Remove advertising instance
clr-adv                                           Clear advertising instances
appearance <appearance>                           Set appearance
version                                           Display version
quit                                              Quit program
exit                                              Quit program
help                                              Display help about this program
export                                            Print evironment variables
"""