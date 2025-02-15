"""WHAD Protocol PHY packet messages abstraction layer.
"""
from whad.protocol.whad_pb2 import Message
from whad.scapy.layers.phy import Phy_Packet
from whad.hub.phy import PhyMetadata
from ..message import pb_bind, PbFieldInt, PbFieldBytes,PbFieldArray, PbMessageWrapper
from . import PhyDomain

from .timestamp import Timestamp

@pb_bind(PhyDomain, 'datarate', 1)
class SetDatarate(PbMessageWrapper):
    """PHY Datarate setting message
    """

    rate = PbFieldInt('phy.datarate.rate')

@pb_bind(PhyDomain, 'endianness', 1)
class SetEndianness(PbMessageWrapper):
    """PHY packet endianness setting message
    """

    endianness = PbFieldInt('phy.endianness.endianness')

@pb_bind(PhyDomain, 'tx_power', 1)
class SetTxPower(PbMessageWrapper):
    """PHY TX power configuration message
    """

    power = PbFieldInt('phy.tx_power.tx_power')

@pb_bind(PhyDomain, 'packet_size', 1)
class SetPacketSize(PbMessageWrapper):
    """PHY packet size configuration message
    """

    packet_size = PbFieldInt('phy.packet_size.packet_size')

@pb_bind(PhyDomain, 'sync_word', 1)
class SetSyncWord(PbMessageWrapper):
    """PHY sync word configuration message
    """

    sync_word = PbFieldBytes('phy.sync_word.sync_word')


@pb_bind(PhyDomain, 'send', 1)
class SendPacket(PbMessageWrapper):
    """PHY packet send message
    """

    packet = PbFieldBytes('phy.send.packet')

    def to_packet(self):
        """Convert message to packet
        """
        return Phy_Packet(self.packet)


    @staticmethod
    def from_packet(packet):
        """Convert packet to message
        """
        return SendPacket(
            packet=bytes(packet)
        )

@pb_bind(PhyDomain, 'send_raw', 1)
class SendRawPacket(PbMessageWrapper):
    """PHY raw packet send message
    """

    iq = PbFieldArray('phy.send_raw.iq')

    def to_packet(self):
        """Convert message to packet
        """
        return Phy_Packet(self.packet)


    @staticmethod
    def from_packet(packet):
        """Convert packet to message
        """
        return SendRawPacket(
            iq=[]
        )

@pb_bind(PhyDomain, 'packet', 1)
class PacketReceived(PbMessageWrapper):
    """PHY packet received notification message
    """

    frequency = PbFieldInt('phy.packet.frequency')
    packet = PbFieldBytes('phy.packet.packet')
    rssi = PbFieldInt('phy.packet.rssi', optional=True)
    timestamp = PbFieldInt('phy.packet.timestamp', optional=True)

    def to_packet(self):
        """Convert message to packet
        """
        packet = Phy_Packet(self.packet)
        packet.metadata = PhyMetadata()
        packet.metadata.frequency = self.frequency
        packet.metadata.raw = False
        if self.rssi is not None:
            packet.metadata.rssi = self.rssi
        if self.timestamp is not None:
            packet.metadata.timestamp = self.timestamp

        return packet

    @staticmethod
    def from_packet(packet):
        """Convert packet to message
        """
        msg = PacketReceived(
            frequency=packet.metadata.frequency,
            packet=bytes(packet)
        )
        if packet.metadata.rssi is not None:
            msg.rssi = packet.metadata.rssi
        if packet.metadata.timestamp is not None:
            msg.timstamp = packet.metadata.timestamp

        return msg

@pb_bind(PhyDomain, 'raw_packet', 1)
class RawPacketReceived(PbMessageWrapper):
    """PHY packet received notification message

    IQ not supported yet.
    """

    frequency = PbFieldInt('phy.raw_packet.frequency')
    packet = PbFieldBytes('phy.raw_packet.packet')
    rssi = PbFieldInt('phy.raw_packet.rssi', optional=True)
    iq = PbFieldArray('phy.raw_packet.iq')
    timestamp = PbFieldInt('phy.raw_packet.timestamp', optional=True)

    def to_packet(self):
        """Convert message to packet
        """
        packet = Phy_Packet(self.packet)
        packet.metadata = PhyMetadata()
        packet.metadata.frequency = self.frequency
        packet.metadata.raw = True
        if self.rssi is not None:
            packet.metadata.rssi = self.rssi
        if self.timestamp is not None:
            packet.metadata.timestamp = self.timestamp

        return packet

    @staticmethod
    def from_packet(packet):
        """Convert packet to message
        """
        msg = PacketReceived(
            frequency=packet.metadata.frequency,
            packet=bytes(packet)
        )
        if packet.metadata.rssi is not None:
            msg.rssi = packet.metadata.rssi
        if packet.metadata.timestamp is not None:
            msg.timestamp = packet.metadata.timestamp

        return msg