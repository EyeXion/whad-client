"""This module provides specific classes to set-up a BLE proxy.

The class :class:`LinkLayerProxy` provides a link-layer level BLE proxy that
will connect to a target device, spawns another device and relay control and
data PDUs between a client and the target device.

The class :class:`GattProxy` provides a GATT BLE proxy that will connect to a
target device, creates another device and relay GATT operations (characteristic
read, write, notification and indication) between a client and the target
device.


"""

from time import sleep
from scapy.layers.bluetooth4LE import BTLE_DATA, BTLE_CTRL
from scapy.layers.bluetooth import L2CAP_Hdr
from whad.domain.ble.connector import BLE, Central, Peripheral, BleDirection
from whad.domain.ble.profile.advdata import AdvDataFieldList, AdvFlagsField, AdvCompleteLocalName
from whad.domain.ble.profile import GenericProfile
from whad.domain.ble.exceptions import HookReturnValue, HookDontForward
from whad.domain.ble.stack.gatt.exceptions import GattTimeoutException
from whad.exceptions import WhadDeviceNotFound
from ....protocol.device_pb2 import Hook

# Logging
import logging
logger = logging.getLogger(__name__)

#############################################
# Link-layer Proxy related classes
#############################################

def is_pdu_valid(pdu):
    if pdu.haslayer(BTLE_DATA):
        btle_data = pdu.getlayer(BTLE_DATA)
        if btle_data.LLID in [0x01, 0x02]:
            return btle_data.haslayer(L2CAP_Hdr)
        else:
            return (btle_data.LLID == 0x03)
    return False

def reshape_pdu(pdu):
    """This function remove any SN/NESN/MD bit as it is usually handled by
    the WHAD BLE-compatible dongle. Some BLE controllers and integrated stacks
    do not like to get PDUs with these bits set.

    :param Packet pdu: Bluetooth LE packet to process
    :return Packet: Clean Bluetooth LE packet
    """
    btle_data = pdu.getlayer(BTLE_DATA)
    payload = btle_data.payload
    return BTLE_DATA(
        LLID=btle_data.LLID,
        len=len(payload)
    )/payload

class LowLevelPeripheral(Peripheral):
    """Link-layer only Peripheral implementation
    """
    def __init__(self, device, adv_data):
        super().__init__(device, adv_data=adv_data)
        self.__connected = False
        self.__conn_handle = None
        self.__other_half = None
        self.__pending_data_pdus = []
        self.__pending_control_pdus = []

    def set_other_half(self, other_half):
        self.__other_half = other_half

    def on_connected(self, connection_data):
        self.__connected = True
        if connection_data.conn_handle is None:
           self.__conn_handle = 0
        else: 
            self.__conn_handle = connection_data.conn_handle

        if len(self.__pending_control_pdus) > 0:
            for _pdu in self.__pending_control_pdus:
                self.send_pdu(_pdu, self.__conn_handle)
        
        if len(self.__pending_data_pdus) > 0:
            for _pdu in self.__pending_data_pdus:
                self.send_pdu(_pdu, self.__conn_handle)

    def on_disconnected(self, connection_data):
        self.__connected = False
        self.__conn_handle = None

    def on_ctl_pdu(self, pdu):
        """This method is called whenever a control PDU is received.
        This PDU is then forwarded to the BLE stack to handle it.

        Peripheral devices act as a slave, so we only forward master to slave
        messages to the stack.
        """
        if pdu.metadata.direction == BleDirection.MASTER_TO_SLAVE:
            if self.__other_half is not None and self.__connected:
                self.__other_half.forward_ctrl_pdu(pdu)

    def on_data_pdu(self, pdu):
        """This method is called whenever a data PDU is received.
        This PDU is then forwarded to the BLE stack to handle it.
        """
        if pdu.metadata.direction == BleDirection.MASTER_TO_SLAVE:
            if self.__other_half is not None and self.__connected:
                self.__other_half.forward_data_pdu(pdu)
            else:
                logger.error('client is not connected to proxy')

    def forward_ctrl_pdu(self, pdu):
        if self.__conn_handle is not None:
            return self.send_pdu(reshape_pdu(pdu), self.__conn_handle)
        else:
            self.__pending_control_pdus.append(reshape_pdu(pdu))

    def forward_data_pdu(self, pdu):
        if self.__conn_handle is not None:
            return self.send_pdu(reshape_pdu(pdu), self.__conn_handle)
        else:
            self.__pending_data_pdus.append(reshape_pdu(pdu))

class LowLevelCentral(Central):
    """Link-layer only Central implementation
    """

    def __init__(self, device):
        super().__init__(device)
        self.__connected = False
        self.__conn_handle = None
        self.__other_half = None

    def set_other_half(self, other_half):
        self.__other_half = other_half

    def is_connected(self):
        return self.__connected

    def peripheral(self):
        return True

    def on_connected(self, connection_data):
        """Override `on_connected` method to avoid notifying the stack. 

        We mark this low-level central as connected and save the connection
        handle.
        """
        self.__connected = True
        if connection_data.conn_handle is None:
           self.__conn_handle = 0
        else: 
            self.__conn_handle = connection_data.conn_handle

    def on_disconnected(self, connection_data):
        logger.info('target device has disconnected')
        self.__connected = False
        self.__conn_handle = None

    def on_ctl_pdu(self, pdu):
        """Forward Control PDU to other half, if connected
        """
        if pdu.metadata.direction == BleDirection.SLAVE_TO_MASTER:
            if self.__other_half is not None and self.__connected:
                self.__other_half.forward_ctrl_pdu(pdu)

    def on_data_pdu(self, pdu):
        """Forward Data PDU to other half, if connected
        """
        if pdu.metadata.direction == BleDirection.SLAVE_TO_MASTER:
            if self.__other_half is not None and self.__connected:
                self.__other_half.forward_data_pdu(pdu)

    def forward_ctrl_pdu(self, pdu):
        if self.__conn_handle is not None:
            return self.send_pdu(reshape_pdu(pdu), self.__conn_handle)
        else:
            logger.error('proxy is not connected to target device')

    def forward_data_pdu(self, pdu):
        if self.__conn_handle is not None:
            return self.send_pdu(reshape_pdu(pdu), self.__conn_handle)
        else:
            logger.error('proxy is not connected to target device')

class LinkLayerProxy(object):
    """This class implements a GATT proxy that relies on two BLE-compatible
    WHAD devices to create a real BLE device that will proxify all the link-layer
    traffic to another device.
    """

    def __init__(self, proxy=None, target=None, adv_data=None, bd_address=None):
        """
        :param BLE proxy: BLE device to use as a peripheral (GATT Server)
        :param BLE target: BLE device to use as a central (GATT Client)
        :param AdvDataFieldList adv_data: Advertising data
        """
        if proxy is None or target is None or bd_address is None:
            raise WhadDeviceNotFound

        if adv_data is None:
            self.__adv_data = AdvDataFieldList(
                AdvFlagsField(),
                AdvCompleteLocalName(b'BleProxy')
            )
        else:
            self.__adv_data = adv_data

        # Save both devices
        self.__proxy = proxy
        self.__central = None
        self.__target = target
        self.__peripheral = None
        self.__target_bd_addr = bd_address

        # Callbacks
        self.__callbacks = []

    def start(self):
        """Start proxy

        The proxy device will be set as a peripheral
        """
        
        # First, connect our central device to our target device
        logger.info('create low-level central device ...')
        self.__central = LowLevelCentral(self.__target)
        logger.info('connecting to target device ...')
        if self.__central.connect(self.__target_bd_addr) is not None:
            logger.info('proxy is connected to target device, create our own device ...')
            
            # Once connected, we start our peripheral
            self.__peripheral = LowLevelPeripheral(
                self.__proxy,
                self.__adv_data
            )
            # Interconnect central and peripheral
            logger.info('proxy peripheral device created, interconnect with central ...')
            self.__peripheral.set_other_half(self.__central)
            self.__central.set_other_half(self.__peripheral)
            logger.info('central and peripheral devices are now interconnected')
            
            # Start advertising
            logger.info('starting advertising our proxy device')
            self.__peripheral.start()
            logger.info('LinkLayerProxy instance is ready')



#############################################
# GATT Proxy related classes
#############################################

class ImportedDevice(GenericProfile):
    def __init__(self, proxy, target, from_json):
        super().__init__(from_json=from_json)
        self.__target = target
        self.__proxy = proxy

    def on_connect(self, conn_handle):
        """This method is called when a device connects to the GATT proxy, and will
        forward this event to the GATT proxy.
        """
        self.__proxy.on_connect(conn_handle)

    def on_disconnect(self, conn_handle):
        """This method is called when a device disconnects from the GATT proxy and
        forwards this event to the proxy itself.
        """
        self.__proxy.on_disconnect(conn_handle)

    def on_characteristic_read(self, service, characteristic, offset=0, length=0):
        """Callback method that handles a characteristic read operation.

        This method accesses the characteristic value and call a proxy-specific
        callback to let the user choose what should be done with this value.

        If the proxy callback raises a :class:`HookReturnValue` exception, the underlying
        GATT stack will take the provided value and return it to the client.

        If no exception is raised then the original characteristic value is returned.
        """
        try:
            # Get characteristic and read its value
            c = self.__target.get_characteristic(service.uuid, characteristic.uuid)
            value = c.read(offset=offset)

            # Call our proxy characteristic read hook
            self.__proxy.on_characteristic_read(
                service,
                characteristic,
                value,
                offset,
                length
            )

            # By default, return characteristic value
            raise HookReturnValue(value)
        except GattTimeoutException as gatt_error:
            logger.error('GATT timeout during characteristic read, return empty data')
            raise HookReturnValue(b'')

    def on_characteristic_write(self, service, characteristic, offset=0, value=b'', without_response=False):
        """Characteristic write hook

        This hook is called whenever a charactertistic is about to be written by a GATT
        client. If this method returns None, then the write operation will return an error.
        """
        c = None

        try:

             # Get target characteristic and write its value
            c = self.__target.get_characteristic(service.uuid, characteristic.uuid)

            self.__proxy.on_characteristic_write(
                service,
                characteristic,
                offset,
                value,
                without_response
            )

            # Write value to target device
            c.write(value)
        except HookReturnValue as write_override:
            c.write(write_override.value)
        except GattTimeoutException as gatt_error:
            logger.error('GATT timeout during characteristic write')
            pass

    def on_characteristic_subscribed(self, service, characteristic, notification=False, indication=False):
        """Characteristic subscription hook.
        """
        try:
            c = self.__target.get_characteristic(service.uuid, characteristic.uuid)
            if notification:
                # Forward callback
                def notif_cb(charac, value, indication=False):
                    try:
                        # Forward to proxy
                        self.__proxy.on_notification(
                            service,
                            characteristic,
                            value
                        )

                        # Update characteristic value
                        characteristic.value = value

                    except HookReturnValue as value_override:
                        # Override value if required
                        characteristic.value = value_override.value

                    except HookDontForward as block:
                        # Don't forward notification
                        pass

                c.subscribe(callback=notif_cb, notification=True)
            elif indication:
                # Forward callback
                def indicate_cb(charac, value, indication=True):
                    try:
                        # Forward to proxy hook.
                        self.__proxy.on_notification(
                            service,
                            characteristic,
                            value
                        )

                        # Update characteristic value
                        characteristic.value = value

                    except HookReturnValue as value_override:
                        # Override value if required
                        characteristic.value = value_override.value

                    except HookDontForward as block:
                        # Don't forward notification
                        pass

                c.subscribe(callback=indicate_cb, indication=True)

            # No action possible here (for now)
            self.__proxy.on_characteristic_subscribed(
                service,
                characteristic,
                notification=notification,
                indication=indication
            )
        except GattTimeoutException as gatt_error:
            logger.error('GATT timeout during characteristic subscribe')

    def on_characteristic_unsubscribed(self, service, characteristic):
        """Characteristic unsubscription hook.
        """
        try:
            c = self.__target.get_characteristic(service.uuid, characteristic.uuid)
            c.unsubscribe()

            # No action possible here (for now)
            self.__proxy.on_characteristic_unsubscribed(
                service,
                characteristic
            )
        except GattTimeoutException as gatt_error:
            logger.error('GATT timeout during characteristic unsubscribe')


class GattProxy(object):
    """GATT Proxy
    """

    def __init__(self, proxy=None, target=None, adv_data=None, bd_address=None):
        self.__proxy_dev = proxy
        self.__target_dev = target
        if adv_data is None:
            self.__adv_data = AdvDataFieldList(
                AdvFlagsField(),
                AdvCompleteLocalName(b'BleProxy')
            )
        else:
            self.__adv_data = adv_data
        self.__target_bd_addr = bd_address


    def on_connect(self, conn_handle):
        logger.info('client connected to proxy')

    def on_disconnect(self, conn_handle):
        logger.info('client disconnected from proxy')

    def on_characteristic_read(self, service, characteristic, value, offset=0, length=0):
        """This callback is called whenever a characteristic is read.

        :param Service service: Service object the target characteristic belongs to.
        :param Characteristic characteristic: Target characteristic object.
        :param bytes value: Characteristic value
        :param int offset: write offset
        :param int length: maximum read length for this characteristic
        """
        logger.info(' << Read characteristic %s: %s' % (characteristic.uuid, value))

    def on_characteristic_write(self, service, characteristic, offset=0, value=b'', without_response=False):
        """This callback is called whenever a characteristic is written.

        Raise a :class:`HookReturnValue` exception to override the value that will be written
        in the target characteristic.

        Raise any other hook exception (:class:`HookReturnAccessDenied`, :class:`HookReturnNotFound`, or
        :class:`HookReturnAuthRequired`) to force the proxy to return a specific error to the
        initiator device.

        :param Service service: Service object the target characteristic belongs to.
        :param Characteristic characteristic: Target characteristic object.
        :param int offset: write offset
        :param bytes value: value to write into this characteristic
        :param bool without_response: True if write operation does not require a response, False otherwise (default: False)
        """
        logger.info(' >> Write characteristic %s with value %s at offset %d' % (characteristic.uuid, value, offset))

    def on_characteristic_subscribed(self, service, characteristic, notification=False, indication=False):
        """This callback is called whenever a characteristic is subscribed to for notification or indication.

        :param Service service: Service object the target characteristic belongs to.
        :param Characteristic characteristic: Target characteristic object.
        :param bool notification: Set to True to subscribe for notification
        :param bool indication: Set to True to subscribe to indication
        """
        logger.info(' ** Subscribed to characteristic %s from service %s' % (characteristic.uuid, service.uuid))

    def on_characteristic_unsubscribed(self, service, characteristic):
        """This callback is called whenever a characteristic is unsubscribed.

        :param Service service: Service object the target characteristic belongs to.
        :param Characteristic characteristic: Target characteristic object.
        """
        logger.info(' ** Unsubscribed to characteristic %s from service %s' % (characteristic.uuid, service.uuid))

    def on_notification(self, service, characteristic, value):
        """This callback is called whenever a notification is received.
        """
        logger.info(' == notification for characteristic %s from service %s: %s' %  (characteristic.uuid, service.uuid, value))

    def on_indication(self, service, characteristic, value):
        """This callback is called whenever a notification is received.
        """
        logger.info(' == indication for characteristic %s from service %s: %s' %  (characteristic.uuid, service.uuid, value))

    def start(self):
        """Start our GATT Proxy
        """
        logger.info('create our central device')
        self.__central = Central(self.__target_dev)
        logger.info('connect to target device')
        self.__target = self.__central.connect(self.__target_bd_addr)
        if self.__target is not None:
            logger.info('connected to target device, discover services and characteristics ...')
            self.__target.discover()
            logger.info('services and characs discovered')
            target_profile = self.__target.export_json()
            
            # Once connected, we start our peripheral
            logger.info('create a peripheral with similar profile ...')
            self.__peripheral = Peripheral(self.__proxy_dev, profile=ImportedDevice(
                self,
                self.__target,
                target_profile
            ))
            self.__peripheral.enable_peripheral_mode(adv_data=self.__adv_data)

            # Start advertising
            logger.info('starting advertising')
            self.__peripheral.start()
            logger.info('GattProxy instance is ready')


