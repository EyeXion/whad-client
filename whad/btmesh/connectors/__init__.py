"""
Bluetooth Mesh Base connector.
================================

Manages basic Tx/Rx. (Based on BLE sniffer because it works)
"""

from whad.ble.connector import Sniffer
from scapy.layers.bluetooth4LE import BTLE_ADV, BTLE_ADV_NONCONN_IND, EIR_Hdr
from whad.ble import UnsupportedCapability, BleDirection, Peripheral
from whad.exceptions import WhadDeviceDisconnected
from queue import Queue, Empty
from time import sleep
from threading import Thread, Lock
from whad.btmesh.crypto import (
    UpperTransportLayerAppKeyCryptoManager,
    UpperTransportLayerDevKeyCryptoManager,
    NetworkLayerCryptoManager,
)

from whad.btmesh.stack import PBAdvBearerLayer
from whad.btmesh.stack.network import NetworkLayer

from whad.btmesh.profile import BaseMeshProfile


# lock for sending to not jam ?
def txlock(f):
    def _wrapper(self, *args, **kwargs):
        self.lock_tx()
        result = f(self, *args, **kwargs)
        self.unlock_tx()
        return result

    return _wrapper


class BTMesh(Sniffer):
    def __init__(
        self, device, profile=BaseMeshProfile(), stack=PBAdvBearerLayer, options={}
    ):
        """
        Creates a Mesh generic Node

        :param device: Whad device handle
        :type device: WhadDeviceConnector
        :param stack: Stack to use, defaults to PBAdvBearerLayer
        :type stack: Stack, optional
        :param options: options de pass to provisioning stack, defaults to {}
        :type options: dict, optional
        :raises UnsupportedCapability: Device Cannot sniff or inject
        """
        super().__init__(device)
        if not self.can_inject():
            raise UnsupportedCapability("Inject")

        self._stack = stack(connector=self, options=options)

        # Queue of received messages, filled in on reception callback
        self.__queue = Queue()

        self.__tx_lock = Lock()

        # The stack used after provisioning (instanced after)
        self._main_stack = None

        self.is_provisioned = False

        self.profile = profile

        self.options = {
            "profile": self.profile,
            "lower_transport": {
                "profile": self.profile,
                "upper_transport": {
                    "profile": self.profile,
                    "access": {"profile": self.profile},
                },
            },
        }

        self.sniffer_channel_switch_thread = Thread(
            target=self.change_sniffing_channel
        ).start()

        self.configure(advertisements=True, connection=False)

        self.polling_rx_packets_thread = None

        self.is_listening = True

    def lock_tx(self):
        self.__tx_lock.acquire()

    def unlock_tx(self):
        self.__tx_lock.release()

    def bt_mesh_filter(self, packet, ignore_regular_adv):
        """
        Filter out non Mesh advertising packets
        """
        if BTLE_ADV in packet:
            if hasattr(packet, "data"):
                if EIR_Hdr in packet and (
                    any([i.type in (0x29, 0x2A, 0x2B) for i in packet.data])
                    or any(
                        h in [[0x1827], [0x1828]]
                        for h in [
                            i.svc_uuids
                            for i in packet.data
                            if hasattr(i, "svc_uuids") and not ignore_regular_adv
                        ]
                    )
                ):
                    return True

    def on_adv_pdu(self, packet):
        """
        Process a received advertising Mesh packet.
        Adds it to queue
        """

        if not self.bt_mesh_filter(packet, True):
            return
        self.__queue.put(packet)

    def start(self):
        super().start()
        self.start_listening()

    def start_listening(self):
        self.is_listening = True
        self.polling_rx_packets_thread = Thread(target=self.polling_rx_packets)
        self.polling_rx_packets_thread.start()

    def stop_listening(self):
        self.is_listening = False

    def polling_rx_packets(self):
        while self.is_listening:
            try:
                self.process_rx_packets(self.__queue.get())
            except Empty:
                sleep(0.001)
            # Handle device disconnection
            except WhadDeviceDisconnected:
                return

    def process_rx_packets(self, packet):
        """
        Process a received Mesh Packet. Logic in subclasses

        :param packet: Packet received
        :type packet: Packet
        """
        # packet.show()
        pass

    @txlock
    def send_raw(self, packet, channel=37):
        """
        Sends the packet through the BLE advertising bearer

        :param packet: Packet to send
        :type packet: Packet (EIR_Element subclass)
        :param channel: [TODO:description], defaults to 37
        :type channel: [TODO:type], optional
        """
        # AdvA = randbytes(6).hex(":")  # random in spec
        AdvA = (self.profile.primary_element_addr & 0xFF).to_bytes(
            1, "big"
        ) + b"\xaa\xaa\xaa\xaa\xaa"
        adv_pkt = BTLE_ADV(TxAdd=0) / BTLE_ADV_NONCONN_IND(AdvA=AdvA, data=packet)
        for i in range(0, 2):
            self.send_pdu(
                adv_pkt,
                access_address=0x8E89BED6,
                conn_handle=39,
                direction=BleDirection.UNKNOWN,
            )
            self.send_pdu(
                adv_pkt,
                access_address=0x8E89BED6,
                conn_handle=37,
                direction=BleDirection.UNKNOWN,
            )
            res = self.send_pdu(
                adv_pkt,
                access_address=0x8E89BED6,
                conn_handle=38,
                direction=BleDirection.UNKNOWN,
            )
            sleep(0.003)
        return res

    def change_sniffing_channel(self):
        channels = [37, 38, 39]
        i = 0
        while True:
            self.channel = channels[i]
            i = (i + 1) % 3
            sleep(0.03)

    def auto_provision(self, net_key, app_key, unicast_addr):
        """
        Auto provisioning with data given in constructor of the connector
        Will automatically bind all the non config models of the node to the primary app key (index 0)

        :param net_key: Primary net key used
        :type primary_net_key: int
        :param app_key: Appkey at index 0, used as dev key as well
        :type app_key: Bytes
        :param unicast_addr: Unicast address of the node
        :type unicast_addr: Bytes
        """
        primary_net_key = NetworkLayerCryptoManager(key_index=0, net_key=net_key)
        dev_key = UpperTransportLayerDevKeyCryptoManager(device_key=app_key)
        primary_app_key = UpperTransportLayerAppKeyCryptoManager(app_key=app_key)
        self.profile.provision(
            primary_net_key,
            dev_key,
            b"\x00\x00\x00\x00",
            0,
            unicast_addr,
            primary_app_key,
        )
        # create app key and bind it to all models
        self.profile.bind_all(primary_app_key.key_index)

        self._main_stack = NetworkLayer(connector=self, options=self.options)

        self.is_provisioned = True

    def do_address(self, address=None):
        """
        Handler for the do_address command in shell.

        Returns the primary address of the node. If address is not None, sets the value to it.
        :param address: Address to set for the Node, defaults to None
        :type address: int, optional
        """
        if address is not None:
            self.profile.set_primary_element_addr(address)

        return self.profile.primary_element_addr


class BTMeshHCI(Peripheral):
    """
    Creates a Mesh generic Node, only using HCI commands

    :param device: Whad device handle
    :type device: WhadDeviceConnector
    :param stack: Stack to use, defaults to PBAdvBearerLayer
    :type stack: Stack, optional
    :param options: options de pass to stack, defaults to {}
    :type options: dict, optional
    :raises UnsupportedCapability: Device Cannot sniff or inject
    """

    def __init__(self, device, stack=PBAdvBearerLayer, options={}):
        super().__init__(device)
