"""WHAD Protocol Hub

The protocol hub is a set of wrappers for Protobuf messages that provides a way
to support different versions of our communication protocol. This protocol hub
provides a default message parser handling different protocol versions that will
pick the correct message wrapper class to parse it. Message wrappers simplifies
the way protocol buffers messages are created by mapping some of their properties
to protobuf messages fields.
"""
from typing import Union
from whad.protocol.whad_pb2 import Message
from .registry import Registry

class ProtocolHub(Registry):
    """WHAD Protocol Hub class

    This class is an interface between all our Python code and the devices, that
    support all the existing versions of the WHAD protocol and handles every
    differences that exist between them in a transparent fashion.
    """

    NAME = 'hub'
    VERSIONS = {}

    def __init__(self, proto_version: int):
        """Instanciate a WHAD protocol hub for a specific version.
        """
        self.__version = proto_version

    @property
    def version(self) -> int:
        return self.__version
    
    @property
    def generic(self):
        return self.get('generic')

    @property
    def discovery(self):
        return self.get('discovery')
    
    @property
    def ble(self):
        return self.get('ble')
    
    @property
    def dot15d4(self):
        return self.get('dot15d4')

    @property
    def phy(self):
        return self.get('phy')
    
    @property
    def esb(self):
        return self.get('esb')
    
    @property
    def unifying(self):
        return self.get('unifying')

    def get(self, factory: str):
        return ProtocolHub.bound(factory, self.__version)(self.__version)

    def parse(self, data: Union[Message, bytes]):
        """Parse a serialized WHAD message into an associated object.
        """
        if isinstance(data, bytes):
            # Use protocol buffers to parse our message
            msg = Message()
            msg.ParseFromString(bytes(data))
        elif isinstance(data, Message):
            msg = data
        else:
            return None

        # Only process generic messages
        return ProtocolHub.bound(
            msg.WhichOneof('msg'),
            self.__version).parse(self.__version, msg)
    
    def convertPacket(self, packet):
        """Convert packet to the corresponding message.
        """
        msg = None

        # We dispatch packets based on their layers
        if self.ble.isPacketCompat(packet):
            msg = self.ble.convertPacket(packet)
        elif self.dot15d4.isPacketCompat(packet):
            msg = self.dot15d4.convertPacket(packet)
        elif self.esb.isPacketCompat(packet):
            msg = self.esb.convertPacket(packet)
        elif self.phy.isPacketCompat(packet):
            msg = self.phy.convertPacket(packet)
        elif self.unifying.isPacketCompat(packet):
            msg = self.unifying.convertPacket(packet)

        return msg
        


from .generic import Generic
from .discovery import Discovery
from .ble import BleDomain
from .dot15d4 import Dot15d4Domain
from .phy import PhyDomain
from .esb import EsbDomain
from .unifying import UnifyingDomain