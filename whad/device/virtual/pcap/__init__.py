from whad.exceptions import WhadDeviceNotFound, WhadDeviceNotReady, WhadDeviceAccessDenied
from whad.device.virtual import VirtualDevice
from whad.helpers import message_filter,is_message_type,bd_addr_to_bytes
from whad.device.virtual.pcap.capabilities import CAPABILITIES
from whad.hub.generic.cmdresult import CommandResult
from whad.hub.dot15d4 import Commands
from scapy.layers.dot15d4 import Dot15d4#, Dot15d4FCS
from whad.ble.utils.phy import channel_to_frequency, frequency_to_channel, crc, FieldsSize, is_access_address_valid
from scapy.utils import PcapReader, PcapWriter
from struct import unpack, pack
from scapy.layers.bluetooth4LE import BTLE
from whad.dot15d4.metadata import Dot15d4Metadata
from whad.ble.metadata import BLEMetadata

from time import sleep
from whad import WhadDomain
from os.path import exists
import logging

logger = logging.getLogger(__name__)

class PCAPDevice(VirtualDevice):

    INTERFACE_NAME = "pcap"

    @classmethod
    def list(cls):
        '''
        Returns a list of available PCAP devices.
        '''
        return None

    @classmethod
    def check_interface(cls, interface):
        '''
        This method checks dynamically if the provided interface can be instantiated.
        '''
        logger.info("Checking interface: %s" % str(interface))
        if interface.endswith(".pcap") or interface.endswith(".pcapng"):
            return True
        else:
            return False

    @property
    def identifier(self):
        '''
        Returns the identifier of the current device (e.g., bus + address in format "<bus>-<address>").
        '''
        return "pcap:" + str(self.__filename)


    def __init__(self, filename):
        """
        Create device connection
        """
        self.__opened = False
        self.__started = False
        self.__filename = filename
        self.__pcap_reader = None
        self.__pcap_writer = None
        self.__dlt = None
        self.__domain = None
        self.__start_timestamp, self.__last_timestamp = None, None
        super().__init__()

    def _is_reader(self):
        """
        Returns True if the PCAP is in reading mode.
        """
        return self.__pcap_reader is not None

    def _get_dlt(self):
        if self._is_reader():
            if hasattr(self.__pcap_reader, "linktype"):
                dlt = self.__pcap_reader.linktype
            else:
                # PCAP-ng
                _ = self.__pcap_reader.read_packet()
                dlt = self.__pcap_reader.interfaces[0][0]
                self.__pcap_reader = PcapReader(self.__filename)
            return dlt

    def _get_domain(self):
        return list(CAPABILITIES[self.__dlt][0].keys())[0]

    def open(self):
        try:
            #print("Opening:", self.__filename)
            if exists(self.__filename):
                logger.info("Existing PCAP file")
                self.__pcap_reader = PcapReader(self.__filename)
                self.__dlt = self._get_dlt()
                self.__domain = self._get_domain()
            else:
                logger.info("No PCAP file")
        except:
            raise WhadDeviceAccessDenied("pcap")

        self._dev_id = self._get_serial_number()
        self._fw_author = self._get_manufacturer()
        self._fw_url = self._get_url()
        self._fw_version = self._get_firmware_version()
        self._dev_capabilities = self._get_capabilities()
        self.__flush = False
        self.__opened = True
        # Ask parent class to run a background I/O thread
        super().open()

    def write(self, data):
        if not self.__opened:
            raise WhadDeviceNotReady()

    def read(self):
        if not self.__opened:
            raise WhadDeviceNotReady()
        while self.__started:
            try:
                if self._is_reader():
                    pkt = self.__pcap_reader.read_packet()
                    self._send_packet(pkt)
            except EOFError:
                sleep(0.5)

    def reset(self):
        pass

    def close(self):
        super().close()

    def _generate_metadata(self, pkt):
        if self.__domain == WhadDomain.Dot15d4:
            metadata = Dot15d4Metadata.convert_from_header(pkt)
        elif self.__domain == WhadDomain.BtLE:
            metadata = BLEMetadata.convert_from_header(pkt)
        else:
            return None
        if self.__start_timestamp is None:
            self.__start_timestamp = metadata.timestamp
        metadata.timestamp = metadata.timestamp - self.__start_timestamp
        return metadata

    def _interframe_delay(self, timestamp):
        if not self.__flush:
            if self.__last_timestamp is None:
                self.__last_timestamp = 0
            sleep((timestamp - self.__last_timestamp)/100000)

    def _send_packet(self, pkt):
        if self.__domain == WhadDomain.Dot15d4:
            metadata = self._generate_metadata(pkt)
            self._interframe_delay(metadata.timestamp)
            self.__last_timestamp = metadata.timestamp
            #pkt.show()
            self._send_whad_zigbee_raw_pdu(bytes(pkt[Dot15d4]), channel=metadata.channel, lqi=metadata.lqi, rssi=metadata.rssi, timestamp=metadata.timestamp)
        elif self.__domain == WhadDomain.BtLE:
            metadata = self._generate_metadata(pkt)
            self._interframe_delay(metadata.timestamp)
            self.__last_timestamp = metadata.timestamp
            self._send_whad_ble_raw_pdu(pkt, metadata)

    def _send_whad_ble_raw_pdu(self, packet, metadata):
        packet = packet[BTLE:]
        access_address = packet.access_addr
        pdu = bytes(packet)[FieldsSize.ACCESS_ADDRESS_SIZE:-FieldsSize.CRC_SIZE]

        # Create a RawPduReceived message
        msg = self.hub.ble.createRawPduReceived(
            metadata.direction,
            pdu,
            access_address,
            0,
            crc_validity=metadata.is_crc_valid,
            crc=packet.crc,
            channel=metadata.channel,
            timestamp=metadata.timestamp,
            rssi=metadata.rssi
        )

        # Send message
        self._send_whad_message(msg)



    # Virtual device whad message builder
    def _send_whad_zigbee_raw_pdu(self, packet, channel=None, rssi=None, lqi=None, is_fcs_valid=True, timestamp=None):
        pdu = packet[:-2]
        fcs = unpack("<H",packet[-2:])[0]

        # Create a RawPduReceived message
        msg = self.hub.dot15d4.createRawPduReceived(
            channel,
            pdu,
            fcs,
            lqi = lqi,
            fcs_validity=is_fcs_valid
        )

        # Set timestamp and RSSI if provided
        if rssi is not None:
            msg.rssi = rssi
        if timestamp is not None:
            msg.timestamp = timestamp

        # Send message
        self._send_whad_message(msg)


    # Virtual device whad message callbacks
    def _on_whad_ble_stop(self, message):
        self.__started = False
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_ble_start(self, message):
        self.__started = True
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_ble_sniff_adv(self, message):
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_ble_sniff_conn(self, message):
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_dot15d4_stop(self, message):
        self.__started = False
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_dot15d4_send_raw(self, message):
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_dot15d4_sniff(self, message):
        self._send_whad_command_result(CommandResult.SUCCESS)

    def _on_whad_dot15d4_start(self, message):
        self.__started = True
        self._send_whad_command_result(CommandResult.SUCCESS)

    # Discovery related functions
    def _get_capabilities(self):
        index = 0 if self._is_reader() else 1
        capabilities = CAPABILITIES[self.__dlt][index]
        return capabilities

    def _get_manufacturer(self):
        return "whad-team".encode('utf-8')

    def _get_serial_number(self):
        return bytes.fromhex("00" * 16)

    def _get_firmware_version(self):
        return (0, 0, 0)

    def _get_url(self):
        return "https://github.com/whad-team/whad-client".encode('utf-8')
