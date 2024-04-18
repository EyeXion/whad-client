"""WHAD Protocol BLE prepared sequences messages abstraction layer.
"""
from whad.protocol.whad_pb2 import Message
from whad.protocol.ble.ble_pb2 import PrepareSequenceCmd
from whad.protocol.hub import pb_bind, PbFieldInt, PbFieldBytes, PbMessageWrapper, \
    PbFieldBool, PbFieldArray, Registry, HubMessage
from whad.protocol.hub.ble import BleDomain

class IPacketSequence:
    """Packet Sequence interface class
    """

    def add_packet(self, packet: bytes):
        """Add packet to the list of packets to send.
        """
        new_pending_pkt = self.message.ble.prepare.sequence.add()
        new_pending_pkt.packet = bytes(packet)

    def get_packet(self, index: int) -> bytes:
        """Get packet from the sequence.
        """
        if index >= 0 and index <= len(self.packets):
            return self.packets[index].packet
        
    def count_packets(self) -> int:
        """Return the number of packets in this prepare sequence message.
        """
        return len(self.packets)

@pb_bind(BleDomain, "prepare_manual", 1)
class PrepareSequenceManual(PbMessageWrapper, IPacketSequence):
    """BLE prepare sequence with manual trigger message class
    """

    sequence_id = PbFieldInt("ble.prepare.id")
    direction = PbFieldInt("ble.prepare.direction")
    direction = PbFieldInt("ble.prepare.direction")
    packets = PbFieldArray("ble.prepare.sequence")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.message.ble.prepare.trigger.manual.CopyFrom(PrepareSequenceCmd.ManualTrigger())

@pb_bind(BleDomain, "prepare_connevt", 1)
class PrepareSequenceConnEvt(PbMessageWrapper, IPacketSequence):
    """BLE prepare sequence with connection event trigger message class
    """
    sequence_id = PbFieldInt("ble.prepare.id")
    direction = PbFieldInt("ble.prepare.direction")
    direction = PbFieldInt("ble.prepare.direction")
    packets = PbFieldArray("ble.prepare.sequence")
    connection_event = PbFieldInt("ble.prepare.trigger.connection_event.connection_event")


@pb_bind(BleDomain, "prepare_pattern", 1)
class PrepareSequencePattern(PbMessageWrapper, IPacketSequence):
    """BLE prepare sequence with reception pattern trigger message class
    """
    sequence_id = PbFieldInt("ble.prepare.id")
    direction = PbFieldInt("ble.prepare.direction")
    direction = PbFieldInt("ble.prepare.direction")
    packets = PbFieldArray("ble.prepare.sequence")
    pattern = PbFieldBytes("ble.prepare.trigger.reception.pattern")
    mask = PbFieldBytes("ble.prepare.trigger.reception.mask")
    offset = PbFieldInt("ble.prepare.trigger.reception.offset")

@pb_bind(BleDomain, "prepare", 1)
class PrepareSequence(Registry):

    def __init__(self, version: int):
        self.proto_version = version

    @staticmethod
    def parse(version: int, message: Message) -> HubMessage:
        """Parses a WHAD BLE PrepareSequence message as seen by protobuf
        """
        trigger_type = message.ble.prepare.trigger.WhichOneof("trigger")
        if trigger_type == 'manual':
            return PrepareSequenceManual.parse(version, message)
        elif trigger_type == 'connection_event':
            return PrepareSequenceConnEvt.parse(version, message)
        elif trigger_type == 'reception':
            return PrepareSequencePattern.parse(version, message)
        else:
            return None

@pb_bind(BleDomain, "triggered", 1)
class Triggered(PbMessageWrapper):
    """BLE prepare sequence triggered message class
    """
    sequence_id = PbFieldInt("ble.triggered.id")
