from threading import Thread, Lock
from queue import Queue, Empty
from binascii import hexlify

# Whad imports
from whad.exceptions import RequiredImplementation, UnsupportedDomain, WhadDeviceNotReady, WhadDeviceNotFound
from whad.protocol.generic_pb2 import ResultCode
from whad.protocol.whad_pb2 import Message
from whad.protocol.device_pb2 import Capability, DeviceDomainInfoResp, DeviceType, DeviceResetQuery
from whad.helpers import message_filter, asciiz
# Logging
import logging
logger = logging.getLogger(__name__)

class WhadDeviceInfo(object):
    """This class caches a device information related to its firmware, type, and supported domains and capabilities.

    :param DeviceInfoResp info_resp:  Whad message containing the device basic information.
    """
    def __init__(self, info_resp):
        # Store device information
        self.__whad_version = info_resp.proto_min_ver
        self.__max_speed = info_resp.max_speed
        self.__fw_author = info_resp.fw_author
        self.__fw_url = info_resp.fw_url
        self.__fw_ver_maj = info_resp.fw_version_major
        self.__fw_ver_min = info_resp.fw_version_minor
        self.__fw_ver_rev = info_resp.fw_version_rev
        self.__device_type = info_resp.type
        self.__device_id = asciiz(info_resp.devid)

        # Parse domains and capabilities
        self.__domains = {}
        self.__commands = {}
        for domain in info_resp.capabilities:
            self.__domains[domain & 0xFF000000] = domain & 0x00FFFFFF
            self.__commands[domain & 0xFF000000] = 0

    def add_supported_commands(self, domain, commands):
        """Adds supported command for a given domain to the device information.

        :param domain: target domain
        :param commands: bitmask representing the supported commands for the given domain
        """
        if domain in self.__domains:
            self.__commands[domain] = commands


    def has_domain(self, domain):
        """Determine if a domain is supported by this device.

        :param Domain domain: Domain to check.
        :returns: True if supported, False otherwise.
        """
        return domain in self.__domains


    def has_domain_cap(self, domain, capability):
        """Check if device supports a specific capability for a given domain.

        :param Domain domain: target domain
        :param Capability capability: capability to check
        """
        if domain in self.__domains:
            return (self.__domains[domain] & (1 << capability) > 0)
        return False


    def get_domain_capabilities(self, domain):
        """Get device domain capabilities.

        :param Domain domain: target domain
        :returns: Domain capabilities
        :rtype: Bitmask of capabilities
        """
        if domain in self.__domains:
            return self.__domains[domain]
        return None


    def get_domain_commands(self, domain):
        """Get supported commands for a specific domain

        :param Domain domain: Target domain
        :returns: Bitmask of supported commands
        """
        if domain in self.__commands:
            return self.__commands[domain]
        return None


    ##### Getters #####

    @property
    def version_str(self):
        """Returns the device firmware version string.

        :returns: Device firmware version string
        """
        return '%d.%d.%d' % (
            self.__fw_ver_maj,
            self.__fw_ver_min,
            self.__fw_ver_rev
        )


    @property
    def whad_version(self):
        """Returns the device supported whad version.
        """
        return self.__whad_version

    @property
    def fw_author(self):
        return self.__fw_author.decode('utf-8')

    @property
    def fw_url(self):
        return self.__fw_url.decode('utf-8')

    @property
    def max_speed(self):
        return self.__max_speed

    @property
    def device_type(self):
        """Returns the device type.
        """
        return self.__device_type

    @property
    def device_id(self):
        """Returns the device id.
        """
        return self.__device_id

    @property
    def domains(self):
        """Return the list of supported domains.
        """
        return self.__domains.keys()


class WhadDeviceConnector(object):
    """
    Device connector.

    A connector creates a link between a device and a protocol controller.
    """

    def __init__(self, device=None):
        """
        Constructor.

        Link the device with this connector, and this connector with the
        provided device.

        :param WhadDevice device: Device to be used with this connector.
        """
        self.set_device(device)
        if self.__device is not None:
            self.__device.set_connector(self)


    def set_device(self, device=None):
        """
        Set device linked to this connector.

        :param WhadDevice device: Device to be used with this connector.
        """
        if device is not None:
            self.__device = device

    @property
    def device(self):
        return self.__device

    # Device interaction
    def send_message(self, message, filter=None):
        """Sends a message to the underlying device without waiting for an answer.

        :param Message message: WHAD message to send to the device.
        :param filter: optional filter function for incoming message queue.
        """
        logger.debug('sending WHAD message to device: %s' % message)
        return self.__device.send_message(message, filter)


    def send_command(self, message, filter=None):
        """Sends a command message to the underlying device and waits for an answer.

        By default, this method will wait for a CmdResult message, but you can provide
        any other filtering function/lambda if you are expecting another message as a
        reply from the device.

        :param Message message: WHAD message to send to the device
        :param filter: Filtering function used to match the expected response from the device.
        """
        return self.__device.send_command(message, filter)

    def wait_for_message(self, timeout=None, filter=None):
        """Waits for a specific message to be received.

        This method reads the message queue and return the first message that matches the
        provided filter. A timeout can be specified and will cause this method to return
        None if this timeout is reached.
        """
        return self.__device.wait_for_message(timeout=timeout, filter=filter)

    # Message callbacks
    def on_discovery_message(self, message):
        """Callback function to process incoming discovery messages.

        This method MUST be overriden by inherited classes.

        :param message: Discovery message
        """
        logger.error('method `on_discovery_message` must be implemented in inherited classes')
        raise RequiredImplementation()

    def on_generic_message(self, message):
        """Callback function to process incoming generic messages.

        This method MUST be overriden by inherited classes.

        :param message: Generic message
        """
        logger.error('method `on_generic_message` must be implemented in inherited classes')
        raise RequiredImplementation()

    def on_domain_message(self, domain, message):
        """Callback function to process incoming domain-related messages.

        This method MUST be overriden by inherited classes.

        :param message: Domain message
        """
        logger.error('method `on_domain_message` must be implemented in inherited classes')
        raise RequiredImplementation()


class WhadDeviceInputThread(Thread):

    """WhadDevice I/O cancellable Thread.

    This thread runs in background and regularly calls the
    device read() method to fetch any incoming data.
    """

    def __init__(self, device):
        super().__init__()
        self.__device = device
        self.__canceled = False

    def cancel(self):
        """
        Cancel current I/O task.
        """
        self.__canceled = True

    def run(self):
        """
        Main task, call device process() method until thread
        is canceled.
        """
        while not self.__canceled:
            self.__device.read()
        logger.info('Device IO thread canceled and stopped.')

class WhadDeviceMessageThread(Thread):

    def __init__(self, device):
        super().__init__()
        self.__device = device
        self.__canceled = False

    def cancel(self):
        """
        Cancel current I/O task.
        """
        self.__canceled = True

    def run(self):
        """
        Main task, call device process_messages() method until thread
        is canceled.
        """
        while not self.__canceled:
            self.__device.process_messages()
        logger.info('Device message thread canceled and stopped.')

class WhadDeviceIOThread(object):

    def __init__(self, device):
        self.__input = WhadDeviceInputThread(device)
        self.__input.daemon = True
        self.__processing = WhadDeviceMessageThread(device)
        self.__processing.daemon = True

    def cancel(self):
        self.__input.cancel()
        self.__processing.cancel()

    def start(self):
        logger.info('starting WhadDevice IO management thread ...')
        self.__input.start()
        self.__processing.start()
        logger.info('WhadDevice IO management thread up and running.')

    def join(self):
        logger.info('waiting for WhadDevice IO management thread to finish ...')
        while self.__input.is_alive() or self.__processing.is_alive():
            self.__input.join(1.0)
            self.__processing.join(1.0)
        logger.info('WhadDevice IO management thread finished.')


class WhadDevice(object):
    """
    WHAD Device interface class.

    This device class handles the device discovery process, every possible
    discovery and generic messages related to the device discovery. It MUST be
    inherited by device handling classes (such as the UartDevice class) in order
    to provide read/write capabilities.

    Inherited classes MUST only implement the following methods:

      * open(): will handle device opening/access
      * close(): will handle device closing
      * read() to read data from the device and send them to on_data_received()
      * write() to send data to the device

    All the message re-assembling, parsing, dispatching and background data reading
    will be performed in this class.
    """

    @classmethod
    def _get_sub_classes(cls):
        """
        Helper allowing to get every subclass of WhadDevice.
        """
        # List every available device class
        device_classes = set()
        for device_class in cls.__subclasses__():
            if device_class.__name__ == "VirtualDevice":
                for virtual_device_class in device_class.__subclasses__():
                    device_classes.add(virtual_device_class)
            else:
                device_classes.add(device_class)
        return device_classes

    @classmethod
    def _create(cls, interface_string):
        """
        Helper allowing to get a device according to the interface string provided.

        To make it work, every device class must implement:
            - a class attribute INTERFACE_NAME, matching the interface name
            - a class method list, returning the available devices
            - a property identifier, allowing to identify the device in a unique way

        This method should NOT be used outside of this class. Use WhadDevice.create instead.
        """
        if interface_string.startswith(cls.INTERFACE_NAME):
            identifier = None
            index = None
            if len(interface_string) == len(cls.INTERFACE_NAME):
                index = 0
            elif interface_string[len(cls.INTERFACE_NAME)] == ":":
                index = None
                try:
                    _, identifier = interface_string.split(":")
                except ValueError:
                    identifier = None
            else:
                try:
                    index = int(interface_string[len(cls.INTERFACE_NAME):])
                except ValueError:
                    index = None

            available_devices = cls.list()
            if index is not None:
                try:
                    return available_devices[index]
                except IndexError:
                    raise WhadDeviceNotFound
            elif identifier is not None:
                for dev in available_devices:
                    if dev.identifier == identifier:
                        return dev
                raise WhadDeviceNotFound
            else:
                raise WhadDeviceNotFound
        else:
            raise WhadDeviceNotFound

    @classmethod
    def create(cls, interface_string):
        '''
        Allows to get a specific device according to the provided interface string.
        The interface string is formed as follow:

        "<device_type>[device_index][:device_identifier]"

        Examples:
            * Instantiating the first available UartDevice:
                "uart" or "uart0"

            * Instantiating the second available UartDevice:
                "uart1"

            * Instantiating an UartDevice linked to /dev/ttyACM0:
                "uart:/dev/ttyACM0"

            * Instantiating the first available UbertoothDevice:
                "ubertooth" or "ubertooth0"

            * Instantiating an UbertoothDevice with serial number "11223344556677881122334455667788":
                ubertooth:11223344556677881122334455667788

        '''
        device_classes = cls._get_sub_classes()

        device = None
        for device_class in device_classes:
            try:
                device = device_class._create(interface_string)
                return device
            except WhadDeviceNotFound:
                continue

        raise WhadDeviceNotFound

    @classmethod
    def list(cls):
        '''
        Returns every available compatible devices.
        '''
        device_classes = cls._get_sub_classes()

        available_devices = []
        for device_class in device_classes:
            for device in device_class.list():
                available_devices.append(device)
        return available_devices

    @property
    def index(self):
        '''
        Returns the current index of the device.
        '''
        devices = self.__class__.list()
        for dev in devices:
            if dev.identifier == self.identifier:
                return devices.index(dev)


    @property
    def interface(self):
        '''
        Returns the current interface of the device.
        '''
        if hasattr(self.__class__,"INTERFACE_NAME"):
            return self.__class__.INTERFACE_NAME + str(self.index)
        else:
            return "unknown"

    @property
    def type(self):
        '''
        Returns the name of the class linked to the current device.
        '''
        return self.__class__.__name__


    def __init__(self):
        # Device information
        self.__info = None
        self.__discovered = False

        # Device connectors
        self.__connectors = []

        # Device IO thread
        self.__io_thread = None

        # Message queues
        self.__messages = Queue()
        self.__msg_queue = Queue()
        self.__mq_filter = None

        # Input pipes
        self.__inpipe = bytearray()

        # Create lock
        self.__lock = Lock()

    def lock(self):
        """Locks the pending output data buffer."""
        self.__lock.acquire()

    def unlock(self):
        """Unlocks the pending output data buffer."""
        self.__lock.release()

    def set_connector(self, connector):
        """
        Set this device connector.

        :param WhadDeviceConnector connector: connector to be used with this device.
        """
        self.__connectors.append(connector)

    ######################################
    # Device I/O operations
    ######################################

    def open(self):
        """
        Open device method. By default, creates a simple thread
        that will handle I/O in background. This requires the object
        to be ready for I/O operations when this method is called.

        This method MUST be overriden by inherited classes.
        """
        self.__io_thread = WhadDeviceIOThread(self)
        self.__io_thread.start()

        # Ask firmware for a reset
        logger.info('resetting device (if possible)')
        self.reset()

    def close(self):
        """
        Close device.

        This method MUST be overriden by inherited classes.
        """
        logger.info('closing WHAD device')

        # Cancel I/O thread
        self.__io_thread.cancel()

        # Send a NOP message to unlock process_messages()
        msg = Message()
        msg.generic.verbose.data=b''
        self.on_message_received(msg)

        # Wait for the thread to terminate nicely.
        self.__io_thread.join()


    def __write(self, data):
        """
        Sends data to the device.

        This is an internal method that SHALL NOT be used from inherited classes.
        """
        self.lock()
        logger.debug('sending %s to WHAD device', bytes(data))
        self.write(bytes(data))
        self.unlock()


    def set_queue_filter(self, filter=None):
        """Sets the message queue filter.

        :param filter: filtering function/lambda to be used by our message queue filter.
        """
        self.__mq_filter = filter

    def wait_for_single_message(self, timeout, filter=None):
        """Configures the device message queue filter to automatically move messages
        that matches the filter into the queue, and then waits for the first message
        that matches this filter and returns it.
        """
        if filter is not None:
            self.set_queue_filter(filter)

        # Wait for a matching message to be caught (blocking)
        return self.__msg_queue.get(block=True, timeout=timeout)


    def wait_for_message(self, timeout=None, filter=None):
        """
        Configures the device message queue filter to automatically move messages
        that matches the filter into the queue, and then waits for the first message
        that matches this filter and process it.

        This method is blocking until a matching message is received.

        :param int timeout: Timeout
        :param filter: Message queue filtering function (optional)
        """
        if filter is not None:
            self.set_queue_filter(filter)

        while True:

            # Wait for a matching message to be caught (blocking)
            msg = self.__msg_queue.get(block=True, timeout=timeout)

            # If message does not match, dispatch.
            if not self.__mq_filter(msg):
                self.dispatch_message(msg)
            else:
                return msg


    def send_message(self, message, keep=None):
        """
        Serializes a message and sends it to the device, without waiting for an answer.
        Optionally, you can update the message queue filter if you need to wait for
        specific messages after the message sent.

        :param Message message: Message to send
        :param keep: Message queue filter function
        """
        logger.info('sending message %s to device' % message)
        # if `keep` is set, configure queue filter
        self.set_queue_filter(keep)

        # Convert message into bytes
        raw_message = message.SerializeToString()


        # Define header
        header = [
            0xAC, 0xBE,
            len(raw_message) & 0xff,
            (len(raw_message) >> 8) & 0xff
        ]

        # Send header followed by serialized message
        self.__write(header)
        self.__write(raw_message)


    def send_command(self, command, keep=None):
        """
        Sends a command and awaits a specific response from the device.
        WHAD commands usualy expect a CmdResult message, if `keep` is not
        provided then this method will by default wait for a CmdResult.

        :param Message command: Command message to send to the device
        :param keep: Message queue filter function (optional)
        :returns: Response message from the device
        :rtype: Message
        """
        # If a queue filter is not provided, expect a default CmdResult
        if keep is None:
            self.send_message(command, message_filter(
                'generic',
                'cmd_result'
            ))
        else:
            self.send_message(command, keep)

        # Retrieve the first message matching our filter.
        return self.wait_for_message()


    def on_data_received(self, data):
        """
        Data received callback.

        This callback will process incoming messages, parse them
        and then forward to the message processing callback.

        :param bytes data: Data received from the device.
        """
        logger.debug('received raw data from device: %s' % hexlify(data))
        messages = []
        self.__inpipe.extend(data)
        while len(self.__inpipe) > 2:
            # Is the magic correct ?
            if self.__inpipe[0] == 0xAC and self.__inpipe[1] == 0xBE:
                # Have we received a complete message ?
                if len(self.__inpipe) > 4:
                    msg_size = self.__inpipe[2] | (self.__inpipe[3] << 8)
                    if len(self.__inpipe) >= (msg_size+4):
                        raw_message = self.__inpipe[4:4+msg_size]
                        _msg = Message()
                        _msg.ParseFromString(bytes(raw_message))
                        logger.debug('WHAD message successfully parsed')
                        self.on_message_received(_msg)

                        # Chomp
                        self.__inpipe = self.__inpipe[msg_size + 4:]
                    else:
                        break
                else:
                    break
            else:
                # Nope, that's not a header
                while (len(self.__inpipe) >= 2):
                    if (self.__inpipe[0] != 0xAC) or (self.__inpipe[1] != 0xBE):
                        self.__inpipe = self.__inpipe[1:]
                    else:
                        break


    def dispatch_message(self, message):
        """Dispatches an incoming message to the corresponding callbacks depending on its
        type and content.

        :param Message message: Message to dispatch
        """
        logger.info('dispatching WHAD message ...')
        if message.WhichOneof('msg') == 'discovery':
            logger.info('message is about device discovery, forwarding to discovery handler')
            self.on_discovery_msg(message.discovery)
        elif message.WhichOneof('msg') == 'generic':
            logger.info('message is generic, forwarding to default handler')
            self.on_generic_msg(message.generic)
        else:
            domain = message.WhichOneof('msg')
            if domain is not None:
                logger.info('message concerns domain `%s`, forward to domain-specific handler' % domain)
                self.on_domain_msg(domain, getattr(message,domain))

    def on_message_received(self, message):
        """
        Method called when a WHAD message is received, dispatching.

        :param Message message: Message received
        """
        # If message queue filter is defined and message matches this filter,
        # move it into our message queue.
        if self.__mq_filter is not None and self.__mq_filter(message):
            #print('msgqueue: %s' % message)
            logger.info('message does match current filter, save it for processing')
            self.__msg_queue.put(message, block=True)
        else:
            # Save message for background dispatch
            logger.info('message does not match filter or no filter set, save in default message queue')
            self.__messages.put(message, block=True)

    def process_messages(self, timeout=1.0):
        """Process pending messages
        """
        try:
            message = self.__messages.get(block=True, timeout=timeout)
            if message is not None:
                self.dispatch_message(message)
        except Empty:
            return None

    ######################################
    # Generic messages handling
    ######################################

    def on_generic_msg(self, message):
        """
        This callback method is called whenever a Generic message is received.

        :param Message message: Generic message received
        """
        # Handle generic result message
        if message.WhichOneof('msg') == 'result':
            if message.result == ResultCode.UNSUPPORTED_DOMAIN:
                logger.error('domain not supported by this device')
                raise UnsupportedDomain()

        # Forward everything to the connectors, if any
        if len(self.__connectors) != 0:
            for connector in self.__connectors:
                connector.on_generic_msg(message)


    ######################################
    # Generic discovery
    ######################################

    def on_discovery_msg(self, message):
        """
        Method called when a discovery message is received. If a connector has
        been associated with the device, forward this message to this connector.
        """

        # Forward everything to the connectors, if any
        if len(self.__connectors) != 0:
            for connector in self.__connectors:
                connector.on_discovery_msg(message)

    def has_domain(self, domain):
        """Checks if device supports a specific domain.

        :param Domain domain: Domain
        :returns: True if domain is supported, False otherwise.
        :rtype: bool
        """
        if self.__info is not None:
            return self.__info.has_domain(domain)


    def get_domains(self):
        """Get device' supported domains.

        :returns: list of supported domains
        :rtype: list
        """
        if self.__info is not None:
            return self.__info.domains


    def get_domain_capability(self, domain):
        """Get a device domain capabilities.

        :param Domain domain: Target domain
        :returns: Domain capabilities
        :rtype: DeviceDomainInfoResp
        """
        if self.__info is not None:
            return self.__info.get_domain_capabilities(domain)

    def get_domain_commands(self, domain):
        """Get a device supported domain commands.

        :param Domain domain: Target domain
        :returns: Bitmask of supported commands
        :rtype: int
        """
        if self.__info is not None:
            return self.__info.get_domain_commands(domain)


    def send_discover_info_query(self, proto_version=0x0100):
        """
        Sends a DeviceInfoQuery message and awaits for a DeviceInfoResp
        answer.
        """
        logger.info('preparing a DeviceInfoQuery message')
        msg = Message()
        msg.discovery.info_query.proto_ver=proto_version
        return self.send_command(
            msg,
            message_filter('discovery', 'info_resp')
        )


    def send_discover_domain_query(self, domain):
        """
        Sends a DeviceDomainQuery message and awaits for a DeviceDomainResp
        answer.
        """
        logger.info('preparing a DeviceDomainInfoQuery message')
        msg = Message()
        msg.discovery.domain_query.domain = domain
        return self.send_command(
            msg,
            message_filter('discovery', 'domain_resp')
        )

    def discover(self):
        """
        Performs device discovery (synchronously).

        Discovery process asks the device to provide its description, including
        its supported domains and associated capabilities. For each domain we
        then query the device and get the list of supported commands.
        """
        if not self.__discovered:
            # We send a DeviceInfoQuery message to the device and expect a
            # DeviceInfoResponse in return.
            resp = self.send_discover_info_query()

            # If we have an answer, process it.
            if resp is not None:
                # Save device information
                self.__info = WhadDeviceInfo(
                    resp.discovery.info_resp
                )

                # Query device domains
                logger.info('query supported commands per domain')
                for domain in self.__info.domains:
                    resp = self.send_discover_domain_query(domain)
                    self.__info.add_supported_commands(
                        resp.discovery.domain_resp.domain,
                        resp.discovery.domain_resp.supported_commands
                    )

                # Mark device as discovered
                logger.info('device discovery done')
                self.__discovered = True

                # Switch to max transport speed
                logger.info('set transport speed to %d' % self.info.max_speed)
                self.change_transport_speed(
                    self.info.max_speed
                )
            else:
                logger.error('device is not ready !')
                raise WhadDeviceNotReady()

    def reset(self):
        """Reset device
        """
        logger.info('preparing a DeviceResetQuery message')
        msg = Message()
        msg.discovery.reset_query.CopyFrom(DeviceResetQuery())
        return self.send_command(
            msg,
            message_filter('discovery', 'ready_resp')
        )

    def change_transport_speed(self, speed):
        """Set device transport speed.

        Optional.
        """
        pass

    @property
    def device_id(self):
        """Return device ID
        """
        return self.__info.device_id

    @property
    def info(self):
        return self.__info

    ######################################
    # Upper layers (domains) handling
    ######################################

    def on_domain_msg(self, domain, message):
        """
        Callback method handling domain-related messages. Since this layer is not
        managed by the root WhadDevice class, forward it to the upper layer, the
        associated connector (if any).

        :param Domain domain: Target domain
        :param Message message: Domain-related message received
        """

        # Forward everything to the connectors, if any
        if len(self.__connectors) != 0:
            for connector in self.__connectors:
                connector.on_domain_msg(domain, message)
        return False


# Defines every supported low-level device
from whad.device.uart import UartDevice
from whad.device.virtual import VirtualDevice

__all__ = [
    'WhadDeviceConnector',
    'WhadDeviceInfo',
    'WhadDevice',
    'UartDevice',
    'VirtualDevice',
]