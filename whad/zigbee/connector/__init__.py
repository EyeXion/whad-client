from scapy.compat import raw
from scapy.config import conf
from scapy.layers.dot15d4 import Dot15d4, Dot15d4FCS
from struct import pack

from whad import WhadDomain, WhadCapability
from whad.scapy.layers.dot15d4tap import Dot15d4TAP_Hdr, Dot15d4TAP_TLV_Hdr, Dot15d4TAP_FCS_Type
from whad.device import WhadDeviceConnector
from whad.helpers import message_filter, is_message_type
from whad.exceptions import UnsupportedDomain, UnsupportedCapability
from whad.zigbee.metadata import generate_zigbee_metadata, ZigbeeMetadata
from whad.protocol.generic_pb2 import ResultCode
from whad.protocol.whad_pb2 import Message
from whad.protocol.zigbee.zigbee_pb2 import Sniff, Start, Stop, StartCmd, StopCmd, \
    Send, SendCmd, EnergyDetection, EnergyDetectionCmd, EndDeviceMode, SetNodeAddress, \
    AddressType

class Zigbee(WhadDeviceConnector):
    """
    Zigbee protocol connector.

    This connector drives a Zigbee-capable device with Zigbee-specific WHAD messages.
    It is required by various role classes to interact with a real device and pre-process
    domain-specific messages.
    """

    def __init__(self, device=None):
        """
        Initialize the connector, open the device (if not already opened), discover
        the services (if not already discovered).
        """
        self.__ready = False
        super().__init__(device)

        # Capability cache
        self.__can_send = None
        self.__can_send_raw = None

        # Open device and make sure it is compatible
        self.device.open()
        self.device.discover()

        # Check if device supports Zigbee
        if not self.device.has_domain(WhadDomain.Zigbee):
            raise UnsupportedDomain()
        else:
            self.__ready = True
            conf.dot15d4_protocol = 'zigbee'

    def close(self):
        self.stop()
        self.device.close()

    def format(self, packet):
        if hasattr(packet, "metadata"):
            header, timestamp = packet.metadata.convert_to_header()
        else:
            header = Dot15d4TAP_Hdr()
            timestamp = None

        header.data.append(Dot15d4TAP_TLV_Hdr()/Dot15d4TAP_FCS_Type(
            fcs_type=int(Dot15d4FCS in packet)
            )
        )
        formatted_packet = header/packet
        return formatted_packet, timestamp

    def _build_scapy_packet_from_message(self, message, msg_type):
        try:
            if msg_type == 'raw_pdu':
                packet = Dot15d4FCS(bytes(message.raw_pdu.pdu) + bytes(pack(">H", message.raw_pdu.fcs)))
                packet.metadata = generate_zigbee_metadata(message, msg_type)
                self._signal_packet_reception(packet)
                return packet

            elif msg_type == 'pdu':
                packet = Dot15d4(bytes(message.pdu.pdu))
                packet.metadata = generate_zigbee_metadata(message, msg_type)
                self._signal_packet_reception(packet)
                return packet

        except AttributeError:
            return None

    def _build_message_from_scapy_packet(self, packet, channel=11):
        msg = Message()

        self._signal_packet_transmission(packet)

        if Dot15d4FCS in packet:
            msg.zigbee.send_raw.channel = channel
            pdu = raw(packet)[:-2]
            msg.zigbee.send_raw.pdu = pdu
            msg.zigbee.send_raw.fcs = packet.fcs

        elif Dot15d4 in packet:
            msg.zigbee.send.channel = channel
            pdu = raw(packet)
            msg.zigbee.send.pdu = pdu
        else:
            msg = None

        return msg

    def can_sniff(self):
        """
        Determine if the device implements a sniffer mode.
        """
        commands = self.device.get_domain_commands(WhadDomain.Zigbee)
        return (
            (commands & (1 << Sniff)) > 0 and
            (commands & (1 << Start))>0 and
            (commands & (1 << Stop))>0
        )


    def can_set_node_address(self):
        """
        Determine if the device can configure a Node address.
        """
        commands = self.device.get_domain_commands(WhadDomain.Zigbee)
        return (
            (commands & (1 << SetNodeAddress)) > 0
        )

    def can_be_end_device(self):
        """
        Determine if the device implements an End Device role mode.
        """
        commands = self.device.get_domain_commands(WhadDomain.Zigbee)
        return (
            (commands & (1 << EndDeviceMode)) > 0 and
            (commands & (1 << Start))>0 and
            (commands & (1 << Stop))>0
        )



    def can_send(self):
        """
        Determine if the device can transmit packets.
        """
        if self.__can_send is None:
            commands = self.device.get_domain_commands(WhadDomain.Zigbee)
            self.__can_send =  (commands & (1 << Send)) > 0
        return self.__can_send


    def can_perform_ed_scan(self):
        """
        Determine if the device can perform energy detection scan.
        """
        commands = self.device.get_domain_commands(WhadDomain.Zigbee)
        return (
            (commands & (1 << EnergyDetection)) > 0 and
            (commands & (1 << Start))>0 and
            (commands & (1 << Stop))>0
        )


    def support_raw_pdu(self):
        """
        Determine if the device supports raw PDU.
        """
        if self.__can_send_raw is None:
            capabilities = self.device.get_domain_capability(WhadDomain.Zigbee)
            self.__can_send_raw = not (capabilities & WhadCapability.NoRawData)
        return self.__can_send_raw

    def sniff_zigbee(self, channel=11):
        """
        Sniff Zigbee packets (on a single channel).
        """
        if not self.can_sniff():
            raise UnsupportedCapability("Sniff")

        msg = Message()
        msg.zigbee.sniff.channel = channel
        resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
        return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

    def set_node_address(self, address, mode=AddressType.SHORT):
        """
        Modify Zigbee node address.
        """
        if not self.can_set_node_address():
            raise UnsupportedCapability("SetNodeAddress")

        msg = Message()
        msg.zigbee.set_node_addr.address = address
        msg.zigbee.set_node_addr.address_type = mode
        resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
        return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

    def set_end_device_mode(self, channel=11):
        """
        Acts as a ZigBee End Device.
        """
        if not self.can_be_end_device():
            raise UnsupportedCapability("EndDevice")

        msg = Message()
        msg.zigbee.end_device.channel = channel
        resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
        return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

    def send(self,pdu,channel=11):
        """
        Send Zigbee packets (on a single channel).
        """
        if self.can_send():
            if self.support_raw_pdu():
                if Dot15d4FCS not in pdu:
                    packet = Dot15d4FCS(raw(pdu)+Dot15d4FCS().compute_fcs(raw(pdu)))
                else:
                    packet = pdu
            elif Dot15d4FCS in pdu:
                pdu = Dot15d4(raw(pdu)[:-2])
            else:
                packet = pdu
            msg = self._build_message_from_scapy_packet(packet, channel)
            resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
            return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

        else:
            return False

    def perform_ed_scan(self, channel=11):
        """
        Perform an Energy Detection scan.
        """
        if self.can_perform_ed_scan():
            msg = Message()
            msg.zigbee.ed.channel = channel
            resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
            return (resp.generic.cmd_result.result == ResultCode.SUCCESS)
        else:
            return False

    def start(self):
        """
        Start currently enabled mode.
        """
        msg = Message()
        msg.zigbee.start.CopyFrom(StartCmd())
        resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
        return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

    def stop(self):
        """
        Stop currently enabled mode.
        """
        msg = Message()
        msg.zigbee.stop.CopyFrom(StopCmd())
        resp = self.send_command(msg, message_filter('generic', 'cmd_result'))
        return (resp.generic.cmd_result.result == ResultCode.SUCCESS)

    def process_messages(self):
        self.device.process_messages()

    def on_generic_msg(self, message):
        pass

    def on_discovery_msg(self, message):
        pass

    def on_domain_msg(self, domain, message):
        if not self.__ready:
            return

        if domain == 'zigbee':

            msg_type = message.WhichOneof('msg')
            if msg_type == 'pdu':
                packet = self._build_scapy_packet_from_message(message, msg_type)
                self.on_pdu(packet)

            elif msg_type == 'raw_pdu':
                packet = self._build_scapy_packet_from_message(message, msg_type)
                self.on_raw_pdu(packet)
            elif msg_type == "ed_sample":
                self.on_ed_sample(message.ed_sample.timestamp, message.ed_sample.sample)

    def on_raw_pdu(self, packet):
        pdu = Dot15d4(raw(packet)[:-2])
        pdu.metadata = packet.metadata
        self.on_pdu(pdu)

    def on_pdu(self, packet):
        pass

    def on_ed_sample(self, timestamp, sample):
        pass


from whad.zigbee.connector.sniffer import Sniffer
from whad.zigbee.connector.enddevice import EndDevice
