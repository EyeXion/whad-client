from whad.ble.connector import BLE
from whad.ble.exceptions import ConnectionLostException
from whad.ble import UnsupportedCapability, message_filter, BleDirection
from whad.hub.ble import Injected
from scapy.layers.bluetooth4LE import BTLE, BTLE_ADV, BTLE_DATA

class Injector(BLE):

    def __init__(self, device, connection=None):
        super().__init__(device)
        self.__connection = connection
        self.__exception = None
        # Check if device accepts injection
        if not self.can_inject():
            raise UnsupportedCapability("Inject")

    def raw_inject(self, packet, channel=37):
        if BTLE in packet:
            access_address = packet.access_addr
        elif BTLE_ADV in packet:
            access_address = 0x8e89bed6
        elif BTLE_DATA in packet:
            if self.__connection is not None:
                access_address = self.__connection.access_address
            else:
                access_address = 0x11223344 # default value

        return self.send_pdu(packet, access_address=access_address, conn_handle=channel, direction=BleDirection.UNKNOWN)

    def inject_to_slave(self, packet):
        if self.__connection is not None:
            self.send_pdu(packet, access_address=self.__connection.access_address, direction=BleDirection.INJECTION_TO_SLAVE)
            message = self.wait_for_message(filter=message_filter(Injected))
            return (message.ble.injected.success, message.injection_attempts)
        else:
            raise self.__exception

    def inject_to_master(self, packet):
        if self.__connection is not None:
            self.send_pdu(packet, access_address=self.__connection.access_address, direction=BleDirection.INJECTION_TO_MASTER)
            message = self.wait_for_message(filter=message_filter(Injected))
            return (message.ble.injected.success, message.injection_attempts)
        else:
            raise self.__exception

    def on_desynchronized(self, access_address):
        if access_address == self.__connection.access_address:
            self.__exception = ConnectionLostException(self.__connection)
            self.__connection = None
