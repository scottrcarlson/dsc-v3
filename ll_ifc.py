#! /usr/bin/env python

"""
This module defines an interface for commanding a LinkLabs module
via the host interface over a serial connection.
"""

from time import time, sleep
from contextlib import contextmanager
from binascii import hexlify
import logging
import struct
from collections import namedtuple
from serial import Serial
from serial.tools import list_ports

LOG = logging.getLogger(__name__)

IRQ_FLAGS = {
    'WDOG_RESET': 0x00000001,
    'RESET': 0x00000002,
    'TX_DONE': 0x00000010,
    'TX_ERROR': 0x00000020,
    'RX_DONE': 0x00000100,
    'CONNECTED': 0x00001000,
    'DISCONNECTED': 0x00002000,
    'CRYPTO_ESTABLISHED': 0x00010000,
    'APP_TOKEN_CONFIRMED': 0x00020000,
    'DOWNLINK_REQUEST_ACK': 0x00040000,
    'INITIALIZATION_COMPLETE': 0x00080000,
    'CRYPTO_ERROR': 0x00100000,
    'APP_TOKEN_ERROR': 0x00200000,
    'ASSERT': 0x80000000,
}

IFC_ACK_CODES = {
    'ACK': 0,
    'NACK_CMD_NOT_SUPPORTED': 1,
    'NACK_INCORRECT_CHKSUM': 2,
    'NACK_PAYLOAD_LEN_OOR': 3,
    'NACK_PAYLOAD_OOR': 4,
    'NACK_BOOTUP_IN_PROGRESS': 5,
    'NACK_BUSY_TRY_AGAIN': 6,
    'NACK_APP_TOKEN_REG': 7,
    'NACK_PAYLOAD_LEN_EXCEEDED': 8,
    'NACK_NOT_IN_MAILBOX_MODE': 9,
    'NACK_OTHER': 255,
}

OPCODES = {
    'VERSION': 0,
    'IFC_VERSION': 1,
    'OP_STATE': 2,
    'OP_TX_STATE': 3,
    'OP_RX_STATE': 4,
    'FREQUENCY': 6,
    'TX_POWER': 7,
    'RESET_SETTINGS': 8,
    'GET_RADIO_PARAMS': 9,
    'SET_RADIO_PARAMS': 10,
    'PKT_SEND_QUEUE': 11,
    'TX_POWER_GET': 12,
    'SYNC_WORD_SET': 13,
    'SYNC_WORD_GET': 14,
    'IRQ_FLAGS': 15,
    'IRQ_FLAGS_MASK': 16,
    'SLEEP': 20,
    'SLEEP_BLOCK': 21,
    'PKT_ECHO': 31,
    'PKT_RECV': 40,
    'MSG_RECV_RSSI': 41,
    'PKT_RECV_CONT': 42,
    'MODULE_ID': 50,
    'STORE_SETTINGS': 51,
    'DELETE_SETTINGS': 52,
    'RESET_MCU': 60,
    'TRIGGER_BOOTLOADER': 61,
    'MAC_MODE_SET': 70,
    'MAC_MODE_GET': 71,
    'PKT_SEND_ACK': 90,
    'PKT_SEND_UNACK': 91,
    'TX_CW': 98,
    'RX_MODE_SET': 110,
    'RX_MODE_GET': 111,
    'QOS_REQUEST': 112,
    'QOS_GET': 113,
    'ANTENNA_SET': 114,
    'ANTENNA_GET': 115,
    'NET_TOKEN_SET': 116,
    'NET_TOKEN_GET': 117,
    'NET_INFO_GET': 118,
    'STATS_GET': 119,
    'RSSI_SET': 120,
    'RSSI_GET': 121,
    'DL_BAND_CFG_GET': 122,
    'DL_BAND_CFG_SET': 123,
    'APP_TOKEN_SET': 124,
    'APP_TOKEN_GET': 125,
    'APP_TOKEN_REG_GET': 126,
    'CRYPTO_KEY_XCHG_REQ': 128,
    'MAILBOX_REQUEST': 129,
    'TIMESTAMP': 131,
    'SEND_TIMESTAMP': 132,
    'HARDWARE_TYPE': 254,
    'FIRMWARE_TYPE': 255,
}

DL_MODES = {
    'off': 0,
    'always': 1,
    'mailbox': 2,
}

ANTENNAS = {
    'ufl': 1,
    'trace': 2,
}

OPEN_NET_TOKEN = hexlify(b'OPEN')

class ModuleConnection(object):
    """
    The interface to a LinkLabs module. The `device` parameter should be a path
    to the module. If none is specified, then the constructor will attempt
    to find one.
    """
    def __init__(self, device=None):
        device = device if device else find_module_device()
        LOG.info("Connecting to %s", device)
        self.sdev = Serial(port=device, baudrate=115200, timeout=1.0)
        if not self.sdev.isOpen():
            raise IOError("Cannot open device %s", device)
        self.frame_start_byte = 0xc4
        self.dummy_byte = 0xff
        self.num_dummy_bytes = 4
        self.message_counter = 0
        self.response_header_length = 5
        self.frame_start_timeout = 1.0

    def close(self):
        """ Closes the serial port owned by this object. """
        self.sdev.close()

    def __enter__(self):
        return self

    def __exit__(self, type_, value, traceback):
        self.close()

    def __str__(self):
        return self.get_unique_id()

    def __repr__(self):
        unique_id = self.get_unique_id()
        device_port = self.sdev.port
        return self.__class__.__name__ + "('{}') -> {}".format(device_port, unique_id)

    def _send_command(self, opcode, send_buff=None):
        """
        Sends a command to the module, waits for the response, and
        returns the response payload.
        """
        self._send_packet(opcode, send_buff if send_buff else [])
        response = self._receive_packet(opcode, self.message_counter)
        self.message_counter = (self.message_counter + 1) % 256

        return response

    def _send_packet(self, opcode, send_buff):
        """ Sends a framed uart transmission to the module. """
        buff = bytearray()

        buff.append(self.frame_start_byte)
        buff.append(opcode)
        buff.append(self.message_counter)

        len_msb = (len(send_buff) >> 8) & 0xFF
        len_lsb = (len(send_buff) >> 0) & 0xFF
        buff.append(len_msb)
        buff.append(len_lsb)

        buff = buff + bytearray(send_buff)

        checksum = compute_checksum(buff)
        buff.append((checksum >> 8) & 0xFF)
        buff.append((checksum >> 0) & 0xFF)

        # Start the buffer with several dummy bytes
        dummy = bytearray([self.dummy_byte] * self.num_dummy_bytes)
        buff = dummy + buff

        LOG.debug("Sending frame %s to %s", hexlify(buff), self.sdev.port)
        written_size = self.sdev.write(buff)
        if written_size != len(buff):
            raise IOError("Not enough bytes written.")
        self.sdev.flush()

    def _receive_packet(self, opcode, message_counter):
        """
        Receive a framed uart transmission from the module. Will return
        the packet payload (without any framing header or CRC).
        """
        start = time()
        while True:
            if time() - start > self.frame_start_timeout:
                raise IOError("Did not get frame start within timeout.")
            byte = self.sdev.read()
            if byte:
                if ord(byte) == self.frame_start_byte:
                    break
                else:
                    LOG.warning("Bad frame start byte: %r", byte)

        resp_header = bytearray(self.sdev.read(self.response_header_length))
        resp_opcode = resp_header[0]
        resp_message_counter = resp_header[1]
        resp_ack = resp_header[2]
        resp_payload_len = (resp_header[3] << 8) + resp_header[4]
        LOG.debug("Received frame header %s from %s", hexlify(resp_header), self.sdev.port)

        if resp_opcode != opcode:
            raise IOError("Did not get the same opcode we sent:\
                Received %s not %s" % (resp_opcode, opcode))
        if resp_message_counter != message_counter:
            raise IOError("Did not get the same message counter we sent.")

        if resp_ack != IFC_ACK_CODES['ACK']:
            nack = next(nack for nack, val in IFC_ACK_CODES.iteritems() if val == resp_ack)
            # Read checksum bytes before raising the exception
            resp_checksum_buff = bytearray(self.sdev.read(2))
            raise IOError(resp_ack, "Received NACK from module: %s" % nack)

        resp_payload = bytearray(self.sdev.read(resp_payload_len))
        LOG.debug("Received frame payload %s from %s", hexlify(resp_payload), self.sdev.port)
        if len(resp_payload) != resp_payload_len:
            raise IOError("Could not read the number of bytes promised by the module.")

        resp_checksum_buff = bytearray(self.sdev.read(2))
        resp_checksum = (resp_checksum_buff[0] << 8) + resp_checksum_buff[1]
        checksum = compute_checksum(bytearray([self.frame_start_byte]) + resp_header + resp_payload)
        if resp_checksum != checksum:
            raise IOError("Checksum mismatch.")

        LOG.debug("Received checksum bytes %s from %s",
                  hexlify(resp_checksum_buff), self.sdev.port)
        self.sdev.flush()

        return resp_payload

    def get_version(self):
        """ Returns the module's firmware version as a tuple of (major, minor, tag). """
        resp_payload = self._send_command(OPCODES['VERSION'])
        return resp_payload[0], resp_payload[1], (resp_payload[2] << 8) + resp_payload[3]

    def set_mac_mode(self, mac):
        """
        Sets the MAC mode of the module. Valid values of the parameter `mac` are
        'Symphony' or 'NoMac'.
        """
        if mac == 'NoMac':
            self._send_command(OPCODES['MAC_MODE_SET'], [0])
        elif mac == 'Symphony':
            self._send_command(OPCODES['MAC_MODE_SET'], [3])
        else:
            raise ValueError("Unknown MAC mode: %s", mac)

    def get_mac_mode(self):
        """ Returns either 'Symphony' or 'NoMac'. """
        resp = self._send_command(OPCODES['MAC_MODE_GET'])
        if resp[0] == 0:
            return 'NoMac'
        elif resp[0] == 3:
            return 'Symphony'
        else:
            raise ValueError("Unknown MAC mode: %s", resp[0])

    def send_message(self, message, ack=False):
        """ Sends an uplink message to the gateway. """
        if len(message) > 256:
            raise ValueError("Message too long. Max message size is 256 bytes.")
        opcode = 'PKT_SEND_ACK' if ack else 'PKT_SEND_UNACK'
        self._send_command(OPCODES[opcode], message)

    def get_irq_flags(self):
        """ Returns a list of irq flags (as strings). """
        resp = self._send_command(OPCODES['IRQ_FLAGS'], [0] * 4)
        flags_int = (resp[0] << 24) + (resp[1] << 16) + (resp[2] << 8) + resp[3]
        return [f for f in IRQ_FLAGS if IRQ_FLAGS[f] & flags_int]

    def clear_irq_flags(self, flags='all'):
        """
        Clears the irq flags. `flags` is a list of irq flag strings. If
        the parameter is not given, then all flags are cleared.
        """
        flag_dict = IRQ_FLAGS if flags == 'all' else {f: IRQ_FLAGS[f] for f in flags}
        flag_int = 0
        for flag_val in flag_dict.itervalues():
            flag_int |= flag_val
        flag_buff = [0xFF & (flag_int >> n) for n in [24, 16, 8, 0]]
        self._send_command(OPCODES['IRQ_FLAGS'], flag_buff)

    def get_unique_id(self):
        """ Returns the UUID of the module. """
        uuid = self._send_command(OPCODES['MODULE_ID'])
        (uuid_int,) = struct.unpack('>Q', uuid)
        uuid_int &= int('1' * 36, 2)
        return "$301$0-0-0-{:09X}".format(uuid_int)

    def delete_settings(self):
        """ Returs the module to factory defaults. """
        self._send_command(OPCODES['DELETE_SETTINGS'])

    def reset_mcu(self):
        """ Reset the module """
        self._send_command(OPCODES['RESET_MCU'])

    def reboot_into_bootloader(self):
        """ Reboots the module into bootloader mode. """
        # Use the _send_packet method because the module
        # reboots before sending the response.
        self._send_packet(OPCODES['TRIGGER_BOOTLOADER'], [])

    def set_network_token(self, token):
        """ Sets the network token for the module. The token should be a hex string. """
        network_token = bytearray.fromhex(token)
        self._send_command(OPCODES['NET_TOKEN_SET'], network_token)

    def get_network_token(self):
        """ Sets the network token for the module. The token should be a hex string. """
        network_token = self._send_command(OPCODES['NET_TOKEN_GET'])
        return hexlify(network_token)

    def set_app_token(self, token):
        """ Sets the application token for the module. The token should be a hex string. """
        app_token = bytearray.fromhex(token)
        self._send_command(OPCODES['APP_TOKEN_SET'], app_token)

    def get_app_token(self):
        """ Sets the application token for the module. The token should be a hex string. """
        app_token = self._send_command(OPCODES['APP_TOKEN_GET'])
        return hexlify(app_token)

    def is_app_token_registered(self):
        """ Returns whether this module's app token has been confirmed by the gateway. """
        return bool(self._send_command(OPCODES['APP_TOKEN_REG_GET'])[0])

    def set_qos(self, qos):
        """
        Requests a quality of service level from the gateway. `qos` can be
        an integer from 0 through 15.
        """
        self._send_command(OPCODES['QOS_REQUEST'], [qos])

    def get_qos(self):
        """ Returns the module's quality of service level. """
        return int(self._send_command(OPCODES['QOS_GET'])[0])

    def set_downlink_mode(self, mode):
        """
        Sets the downlink mode of the module.
        Valid modes are 'off', 'always', and 'mailbox'.
        """
        self._send_command(OPCODES['RX_MODE_SET'], [DL_MODES[mode]])

    def get_downlink_mode(self):
        """ Returns a boolean indicating whether or not the module is in downlink mode. """
        dl_mode_int = self._send_command(OPCODES['RX_MODE_GET'])[0]
        for mode in DL_MODES:
            if DL_MODES[mode] == dl_mode_int:
                return mode
        raise RuntimeError("Unknown downlink mode: {}".format(dl_mode_int))

    def retrieve_packet(self):
        """
        Get a downlink packet from the module.
        Returns the packet, as well as RSSI and SNR values.
        """
        buff = self._send_command(OPCODES['MSG_RECV_RSSI'], [0, 0])
        if buff:
            (rssi, ) = struct.unpack_from('<h', bytes(buff[:2]))
            snr = buff[2]
            message = buff[3:]
            return message, rssi, snr

    def get_network_info(self):
        """ Gets current network info from the module. Returns a NetworkInfo object. """
        net_info_struct_str = '>LLbLLhbBBQ'
        info = NetworkInfo(*struct.unpack_from(net_info_struct_str,
                                               bytes(self._send_command(OPCODES['NET_INFO_GET']))))

        # Convert some values from integers.
        info = info._replace(network_id_node='{:8X}'.format(info.network_id_node),
                             network_id_gw='{:8X}'.format(info.network_id_gw),
                             gateway_id='$101$0-0-0-{:8x}'.format(info.gateway_id),
                             scanning=bool(info.scanning))

        if info.connection_status == 0:
            info = info._replace(connection_status='Initializing')
        elif info.connection_status == 1:
            info = info._replace(connection_status='Disconnected')
        elif info.connection_status == 2:
            info = info._replace(connection_status='Connected')

        return info

    def get_state(self):
        """ Returns a triple: (state, tx_state, rx_state) """
        states = {1: 'Connected', 2: 'Disconnected', 3: 'Initializing', 255: 'Error'}
        state = states[self._send_command(OPCODES['OP_STATE'])[0]]

        tx_states = {1: 'Transmitting', 2: 'Success', 255: 'Error'}
        tx_state = tx_states[self._send_command(OPCODES['OP_TX_STATE'])[0]]

        rx_states = {0: 'NoMsg', 1: 'Msg'}
        rx_state = rx_states[self._send_command(OPCODES['OP_RX_STATE'])[0]]

        return (state, tx_state, rx_state)

    def mailbox_request(self):
        """ Pings the gateway to check this module's mailbox. """
        self._send_command(OPCODES['MAILBOX_REQUEST'])

    def set_antenna(self, antenna):
        """ Sets the antenna. The `antenna` argument must be 'trace' or 'ufl'. """
        self._send_command(OPCODES['ANTENNA_SET'], [ANTENNAS[antenna]])

    def get_antenna(self):
        """ Gets the current active antenna. Returns either 'ufl' or 'trace'. """
        antenna_byte = self._send_command(OPCODES['ANTENNA_GET'])[0]
        for (antenna, antenna_num) in ANTENNAS.items():
            if antenna_num == antenna_byte:
                return antenna

        raise RuntimeError("Unknown antenna number")


NetworkInfo = namedtuple('NetworkInfo', ['network_id_node', 'network_id_gw', 'gateway_channel',
                                         'gateway_frequency', 'last_rx_tick', 'rssi', 'snr',
                                         'connection_status', 'scanning', 'gateway_id'])


class ModuleDriver(ModuleConnection):
    """
    This class extends the ModuleConnection class to provide higher level
    functionality.
    """
    def __init__(self, *args, **kwargs):
        super(ModuleDriver, self).__init__(*args, **kwargs)
        self.connection_timeout_s = 2 * 60.0
        self.app_token_confirm_timeout = 60.0
        self.transmit_timeout = 60.0

    def wait_for_flags(self, flags, timeout, bad_flags=None):
        """ Waits for all flags in `flags` to show up. """
        start = time()
        while time() - start < timeout:
            mod_flags = self.get_irq_flags()
            if bad_flags:
                for flag in bad_flags:
                    if flag in mod_flags:
                        raise BadFlagError(flag)
            if all(f in mod_flags for f in flags):
                break
            else:
                sleep(0.1)
        else:
            raise RuntimeError("Timeout waiting for flags {}".format(flags))

    def set_up(self, app_token, network_token=OPEN_NET_TOKEN, qos=0, downlink_mode='off', factory_reset=False):
        """
        Sets up the module so that it's ready to uplink or downlink.
        Throws an exception if it can't connect to a gateway with the provided network
        and application tokens.
        """

        if factory_reset:
            LOG.info("Resetting module %s.", self)
            self.delete_settings()
            sleep(3)

        self.set_mac_mode('Symphony')

        self.set_network_token(network_token)
        self.set_app_token(app_token)
        self.set_qos(qos)
        self.set_downlink_mode(downlink_mode)

        timeout_s = 120.0
        start = time()
        while time() - start < timeout_s:
            (state, _, _) = self.get_state()
            if state == 'Initializing':
                LOG.debug("Initializing...")
            elif state == 'Connected':
                LOG.info("Successfully set up %s", self)
                break
            elif state == 'Disconnected':
                raise RuntimeError("{} could not connect to a gateway".format(self))
            else:
                raise RuntimeError("Error setting up {}: {}".format(self, state))
        else:
            raise RuntimeError("Timeout in setting up {}".format(self))

    def send_message_checked(self, message):
        """
        Sends an ACK'd message, and waits for the status of that message.
        Throws an exception if the message was not successful.
        """
        self.clear_irq_flags(['TX_DONE', 'TX_ERROR'])
        self.send_message(message, ack=True)

        LOG.debug("Waiting for ACK for module %s.", self)
        self.wait_for_flags(['TX_DONE'], self.transmit_timeout, bad_flags=['TX_ERROR'])

    def get_received_message(self):
        """
        Returns a downlink message if there is one, else returns None
        """
        if 'RX_DONE' in self.get_irq_flags():
            self.clear_irq_flags(['RX_DONE'])
            pkt = self.retrieve_packet()
            if pkt is None:
                LOG.warning("RX_DONE flag set but no packet available.")
            return pkt


def compute_checksum(buff):
    """ Computes the 16-bit CRC of the buffer. Returns the checksum as an integer. """
    checksum = 0
    for byte in buff:
        checksum = ((checksum >> 8)|(checksum << 8)) & 0xFFFF
        checksum = checksum ^ byte
        checksum = checksum ^ ((checksum & 0xFF) >> 4)
        checksum = checksum ^ ((checksum << 12) & 0xFFFF)
        checksum = checksum ^ ((checksum & 0xFF) << 5)
    return checksum


class BadFlagError(Exception):
    pass


@contextmanager
def get_all_modules():
    """
    Finds all attached modules, and returns a list of ModuleDriver objects
    for each one.

    This function uses contextmanager to automatically close each module's serial connection
    after you're done with it. This means you'll have to use the function with the `with`
    keyword. For example:

    with get_all_modules() as mods:
        for mod in mods:
            print mod.get_version()
    """
    mods = [ModuleDriver(dev) for [dev, _, _] in list_ports.grep('10c4:ea60')]
    yield mods
    for mod in mods:
        mod.close()


def find_module_device():
    """ Finds the first CP210x device. """
    port = next(list_ports.grep('10c4:ea60'), None)
    if port:
        [name, _, _] = port
        return name
    else:
        raise RuntimeError('LinkLabs module not found')
