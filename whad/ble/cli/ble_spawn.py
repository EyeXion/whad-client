"""Bluetooth Low Energy emulation tool

This utility will configure a compatible whad device to connect to a given
BLE device, and chain this with another tool.

"""
import json
import logging
from time import sleep

from whad.cli.app import CommandLineDevicePipe, run_app
from whad.device import Bridge
from whad.device.connector import LockedConnector
from whad.device.unix import UnixSocketServerDevice, UnixConnector
from whad.hub.ble import Connected, Disconnected, BlePduReceived, BleRawPduReceived, \
    BDAddress
from whad.ble.connector import Peripheral
from whad.hub.discovery import Capability, Domain

logger = logging.getLogger(__name__)

class BleSpawnOutputPipe(Bridge):
    """wble-spawn output pipe
    """

    def __init__(self, input_connector, output_connector):
        """Custom output pipe, will make sure to forward queued PDUs from
        input_connector to output_connector.
        """
        # Retrieve an instance of our protocol hub
        self.hub = input_connector.hub

        # Do we get raw PDUs ?
        if input_connector.support_raw_pdu():
            self.support_raw_pdu = True
        else:
            self.support_raw_pdu = False

        # Save input connector connection handle, as we are supposed to be
        # connected.
        self.__in_handle = input_connector.conn_handle

        # This will dissociate the underlying devices from our connectors.
        # Our central proxy will no more store queued packets, so we are left
        # with the ones we already captured.
        super().__init__(input_connector, output_connector)


    def convert_packet_message(self, message, ingress=True):
        """Convert a BleRawPduReceived/BlePduReceived notification into the
        corresponding SendBleRawPdu/SendBlePdu command, using the provided
        connection handle.
        """
        if ingress:
            connector = self.input
        else:
            connector = self.output

        # Do we received a packet notification ?
        logger.debug("[ble-spawn][output-pipe] convert message %s into a command", message)
        if isinstance(message, BleRawPduReceived):
            # Does our input connector support raw packets ?
            if connector.support_raw_pdu():
                logger.debug("[ble-spawn][output-pipe] connector supports raw pdu")
                # Create a SendBleRawPdu command
                command = connector.hub.ble.create_send_raw_pdu(
                    message.direction,
                    message.pdu,
                    message.crc,
                    encrypt=False,
                    access_address=message.access_address,
                    conn_handle=message.conn_handle, # overwrite the connection handle
                )
                logger.debug("[ble-spawn][output-pipe] created command %s", command)
            else:
                logger.debug("[ble-spawn][output-pipe] connector does not support raw pdu")
                # Create a SendBlePdu command
                command = connector.hub.ble.create_send_pdu(
                    message.direction,
                    message.pdu,
                    self.__in_handle, # overwrite the connection handle
                    encrypt=False
                )
                logger.debug("[ble-spawn][output-pipe] created command %s", command)
        elif isinstance(message, BlePduReceived):
            # Does our input connector support raw packets ?
            if connector.support_raw_pdu():
                logger.debug("[ble-spawn][output-pipe] connector supports raw pdu")
                # Create a SendBleRawPdu command
                command = connector.hub.ble.create_send_raw_pdu(
                    message.direction,
                    message.pdu,
                    None,
                    encrypt=False,
                    access_address=0x11223344, # We use the default access address
                    conn_handle=self.__in_handle, # overwrite the connection handle
                )
                logger.debug("[ble-spawn][output-pipe] created command %s", command)
            else:
                logger.debug("[ble-spawn][output-pipe] connector does not support raw pdu")
                # Create a SendBlePdu command
                command = self.input.hub.ble.create_send_pdu(
                    message.direction,
                    message.pdu,
                    self.__in_handle, # overwrite the connection handle
                    encrypt=False
                )
                logger.debug("[ble-spawn][output-pipe] created command %s", command)
        else:
            # Not a BLE packet notification
            command = None

        # Return generated command
        return command

    def on_inbound(self, message):
        """Process inbound messages.

        Inbound packets are packets coming from our output connector, i.e. the
        central device connected to our emulated peripheral, that need to be
        forwarded as packets to the previous tool.

        Normally, since we get packets from a central device we are supposed to
        be connected and know the connection handle corresponding to this
        connection.
        """
        logger.info("spawn inbound: %s", message)
        if isinstance(message, (BleRawPduReceived, BlePduReceived)):
            logger.debug(
                "[ble-spawn][output-pipe] received an inbound PDU message %s",
                message
            )
            command = self.convert_packet_message(message, True)
            self.input.send_command(command)
        else:
            super().on_inbound(message)

    def on_outbound(self, message):
        logger.info("spawn outbound: %s", message)

        # Update connection handle if a new connection is created
        if isinstance(message, Connected):
            logger.debug(
                "[wble-spawn][output-pipe] new connection, update connection handle to %d",
                message.conn_handle
            )
            self.__in_handle = message.conn_handle

            # If input interface has been locked, unlock it.
            if self.input.is_locked():
                self.input.unlock()
        elif isinstance(message, Disconnected):
            logger.debug(
                "[wble-spawn][output-pipe] Central has just disconnected."
            )
            # We are now disconnected, we must lock our input interface
            self.input.lock()

        # Forward the message to the bridged interface
        super().on_outbound(message)

class BleSpawnInputPipe(Bridge):
    """ble-spawn input pipe

    When ble-spawn is chained after another whad tool, it spawns a device
    based on the specified profile using the specified WHAD adapter, awaits for
    a connection and then send every receive packets to the previous tool as
    well as relay packets it receives to the connected central device.
    """

    def __init__(self, input_connector, output_connector):
        """Initialize our ble-spawn input pipe.
        """
        self.__output_pending_packets = []

        # Do we get raw PDUs ?
        if output_connector.support_raw_pdu():
            self.support_raw_pdu = True
        else:
            self.support_raw_pdu = False

        logger.debug('[ble-spawn][input-pipe] Initialization')
        super().__init__(input_connector, output_connector)

        logger.debug('[ble-spawn][input-pipe] Initialize properties')
        self.__connected = False
        self.__in_conn_handle = None
        self.__out_conn_handle = None

    def set_in_conn_handle(self, conn_handle: int):
        """Saves the input connector connection handle.
        """
        self.__in_conn_handle = conn_handle

    def set_out_conn_handle(self, conn_handle: int):
        """Saves output connection handle.
        """
        logger.debug("[ble-spawn][input-pipe] set output connection handle to %d", conn_handle)
        self.__out_conn_handle = conn_handle

    def convert_packet_message(self, message, conn_handle, ingress=True):
        """Convert a BleRawPduReceived/BlePduReceived notification into the
        corresponding SendBleRawPdu/SendBlePdu command, using the provided
        connection handle.
        """
        if ingress:
            connector = self.input
        else:
            connector = self.output

        # Do we received a packet notification ?
        logger.debug("[ble-spawn][input-pipe] convert message %s into a command", message)
        if isinstance(message, BleRawPduReceived):
            # Does our input connector support raw packets ?
            logger.debug("[ble-spawn][input-pipe] connector does not support raw pdu")
            # Create a SendBlePdu command
            command = connector.hub.ble.create_send_pdu(
                message.direction,
                message.pdu,
                conn_handle, # overwrite the connection handle
                encrypt=False
            )
            logger.debug("[ble-spawn][input-pipe] created command %s", command)
        elif isinstance(message, BlePduReceived):
            # Does our input connector support raw packets ?
            logger.debug("[ble-spawn][input-pipe] connector does not support raw pdu")
            # Create a SendBlePdu command
            command = self.input.hub.ble.create_send_pdu(
                message.direction,
                message.pdu,
                conn_handle, # overwrite the connection handle
                encrypt=False
            )
            logger.debug("[ble-spawn][input-pipe] created command %s", command)
        else:
            # Not a BLE packet notification
            command = None

        # Return generated command
        return command

    def on_inbound(self, message):
        """Process inbound messages.

        Inbound packets are packets coming from our output connector, i.e. the
        central device connected to our emulated peripheral, that need to be
        forwarded as packets to the previous tool.

        Normally, since we get packets from a central device we are supposed to
        be connected and know the connection handle corresponding to this
        connection.
        """
        if isinstance(message, (BleRawPduReceived, BlePduReceived)):
            if not self.__connected:
                logger.debug(
                    "[ble-spawn][input-pipe] add pending inbound PDU message %s to queue",
                    message
                )
            else:
                logger.debug(
                    "[ble-spawn][input-pipe] received an inbound PDU message %s",
                    message
                )
                command = self.convert_packet_message(message, self.__in_conn_handle, True)
                self.input.send_command(command)
        elif isinstance(message, Disconnected):
            # Central device has disconnected, we don't care but we don't send this
            # notification to our chained tool.
            logger.debug('[ble-spawn][input-pipe] received a disconnection notification, discard')
            return
        elif isinstance(message, Connected):
            logger.debug((
                "[ble-spawn][input-pipe] received a connection notification, "
                "update input conn_handle to %d"),
                message.conn_handle
            )
            # Central device has connected, update our output connection handle.
            self.set_out_conn_handle(message.conn_handle)
            self.__connected = True

            # Send pending packets, if any
            for message in self.__output_pending_packets:
                logger.debug('[ble-spawn][input-pipe] process pending PDU message %s', message)
                command = self.convert_packet_message(message, self.__out_conn_handle, False)
                self.output.send_command(command)
        else:
            logger.debug("[ble-spawn][input-pipe] forward default inbound message %s", message)
            # Forward other messages
            super().on_inbound(message)

    def on_outbound(self, message):
        """Process outbund messages.
        """
        if isinstance(message, (BleRawPduReceived, BlePduReceived)):
            if self.__out_conn_handle is not None:
                logger.debug("[ble-spawn][input-pipe] received an outbound PDU message %s", message)
                command = self.convert_packet_message(message, self.__out_conn_handle, False)
                self.output.send_command(command)
            else:
                logger.debug("[ble-spawn][input-pipe] not connected but received %s", message)
                # Save packet as message in pending packets
                self.__output_pending_packets.append(message)
        elif isinstance(message, Connected):
            # Don't forward this message.
            logger.debug("[ble-spawn][input-pipe] received a connection notification, discard")
            return
        elif isinstance(message, Disconnected):
            # Chained tool has lost connection, we must handle it
            logger.debug("[ble-spawn][input-pipe] received a disconnection notification, discard")
            return
        else:
            logger.debug("[ble-spawn][input-pipe] forward default outbound message %s", message)
            # Forward other messages
            super().on_outbound(message)


class BleSpawnApp(CommandLineDevicePipe):
    """Bluetooth Low Energy device spawning tool.
    """

    MODE_END_CHAIN = 0
    MODE_START_CHAIN = 1

    def __init__(self):
        """Application uses an interface and has commands.
        """
        super().__init__(
            description='WHAD Bluetooth Low Energy device emulation tool',
            interface=True,
            commands=False
        )

        self.add_argument(
            '--profile',
            '-p',
            dest='profile',
            help='Use a saved device profile'
        )

        self.__mode = ''
        self.input_conn_handle = None
        self.output_conn_handle = None

    def run(self):
        """Override App's run() method to handle scripting feature.
        """
        try:
            # Launch pre-run tasks
            self.pre_run()

            # We need to have an interface specified
            if self.interface is not None:

                if self.args.profile is not None:
                    try:
                        # Load file content
                        with open(self.args.profile,'rb') as profile:
                            profile_json = profile.read()
                            profile = json.loads(profile_json)

                        adv_data = bytes.fromhex(profile["devinfo"]["adv_data"])
                        scan_rsp = bytes.fromhex(profile["devinfo"]["scan_rsp"])

                        # If stdin is piped, we are supposed to advertise a device and
                        # proxify once connected
                        if self.is_stdin_piped() and not self.is_stdout_piped():
                            # We create a peripheral that will send all packets to our input interface
                            self.__mode = self.MODE_END_CHAIN
                            self.create_input_proxy(adv_data, scan_rsp, int(self.args.conn_handle),
                                                    profile)

                        # Else if stdout is piped, we are supposed to advertise a device
                        # and proxify when connected
                        elif self.is_stdout_piped() and not self.is_stdin_piped():
                            # We create a peripheral that will proxy all messages
                            self.__mode = self.MODE_START_CHAIN
                            self.create_output_proxy(adv_data, scan_rsp, profile_json)
                        else:
                            self.error('Tool must be piped to another WHAD tool.')
                    except FileNotFoundError:
                        self.error(f"Profile file not found ({self.args.profile}).")
                    except IOError:
                        self.error(f"Cannot read file ({self.args.profile}).")
                else:
                    self.error("You need to specify a profile file with option --profile.")
            else:
                self.error("You need to specify an interface with option --interface.")

        except KeyboardInterrupt:
            self.warning("ble-spawn stopped (CTL-C)")

        # Launch post-run tasks
        self.post_run()

    def create_input_proxy(self, adv_data: bytes, scan_data: bytes, conn_handle, profile):
        """Configure our hardware to advertise a BLE peripheral, and once
        a central device is connected relay all packets to our input_interface.
        """
        self.input_conn_handle = int(self.args.conn_handle)

        # Extract address info from profile
        address = profile["devinfo"]["bd_addr"]
        address_type = profile["devinfo"]["addr_type"]

        # Create our peripheral
        logger.info("[ble-spawn] Creating peripheral ...")
        peripheral = Peripheral(self.interface, adv_data=adv_data, scan_data=scan_data,
                                bd_address=address, public=address_type==BDAddress.PUBLIC)

        # Query the input device to check if it supports raw BLE packets
        self.input_interface.discover()
        capabilities = self.input_interface.get_domain_capability(Domain.BtLE)
        can_send_raw = not (capabilities & Capability.NoRawData)
        if can_send_raw and not peripheral.support_raw_pdu():
            self.warning((
                "WHAD interface used as fake BLE device does not support raw PDUs, "
                "while the other end does.\n    Some control PDUs may be lost in"
                "this packet processing chain and may cause issues !"
            ))

        # Query the input device to check if it supports raw BLE packets
        self.input_interface.discover()
        capabilities = self.input_interface.get_domain_capability(Domain.BtLE)
        can_send_raw = not (capabilities & Capability.NoRawData)
        if can_send_raw and not peripheral.support_raw_pdu():
            self.warning((
                "WHAD interface used as fake BLE device does not support raw PDUs, "
                "while the other end does.\n    Some control PDUs may be lost in"
                "this packet processing chain and may cause issues !"
            ))

        # Create our packet bridge
        logger.info("[ble-spawn] Starting our input pipe")
        input_pipe = BleSpawnInputPipe(LockedConnector(self.input_interface), peripheral)
        input_pipe.set_in_conn_handle(conn_handle)

        # Loop until the user hits CTL-C
        while self.input_interface.opened:
            sleep(.2)

    def create_output_proxy(self, adv_data, scan_data, profile_json):
        """Create an output proxy that will relay packets from our emulated BLE
        peripheral to a chained tool.
        """
        # Create our peripheral
        logger.info("[ble-spawn] Creating peripheral ...")
        peripheral = Peripheral(self.interface, adv_data=adv_data, scan_data=scan_data)
        peripheral.lock()
        peripheral.wait_connection()

        # Create our unix socket server
        unix_server = UnixConnector(UnixSocketServerDevice(parameters={
            'domain': 'ble'
        }))

        # Create our packet bridge
        logger.info("[ble-spawn] Starting our output pipe")
        _ = BleSpawnOutputPipe(peripheral, unix_server)

        # Loop until the user hits CTL-C
        while unix_server.device.opened:
            sleep(.2)

        logger.warning("Unix socket client disconnected")

def ble_spawn_main():
    """BLE device spawning tool main routine.
    """
    app = BleSpawnApp()
    run_app(app)
