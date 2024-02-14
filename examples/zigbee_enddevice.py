from whad.device import WhadDevice
from whad.zigbee import EndDevice
from whad.common.monitors import WiresharkMonitor
from whad.exceptions import WhadDeviceNotFound
from scapy.compat import raw
import sys

def show(pkt):
    if hasattr(pkt, "metadata"):
        print(pkt.metadata, bytes(pkt).hex(), repr(pkt))

if __name__ == '__main__':
    if len(sys.argv) >= 2:
        # Retrieve target interface

        interface = sys.argv[1]

        try:
            monitor = WiresharkMonitor()

            dev = WhadDevice.create(interface)
            end_device = EndDevice(dev)
            monitor.attach(end_device)
            monitor.start()
            input()
            end_device.attach_callback(show)
            end_device.start()

            selected_network = None
            print("[i] Discovering networks.")
            for network in end_device.discover_networks():
                print("[i] Network detected: ", network)
                if network.extended_pan_id == 0xf4ce3673877b2d89:
                    selected_network = network

            while True:
                input()
        except (KeyboardInterrupt, SystemExit):
            dev.close()

        except WhadDeviceNotFound:
            print('[e] Device not found')
            exit(1)
    else:
        print('Usage: %s [device]' % sys.argv[0])
