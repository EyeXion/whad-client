from whad.ble import Peripheral
from whad.common.monitors import WiresharkMonitor
from whad.ble.profile.advdata import AdvCompleteLocalName, AdvDataFieldList, AdvFlagsField
from whad.ble.profile.attribute import UUID
from whad.ble.profile import PrimaryService, Characteristic, GenericProfile
from whad.ble.stack.smp import Pairing, IOCAP_NOINPUT_NOOUTPUT
from whad.device.uart import WhadDevice
from time import sleep
import sys

def show(packet):
    print(packet.metadata, repr(packet))

class MyPeripheral(GenericProfile):

    device = PrimaryService(
        uuid=UUID(0x1800),

        device_name = Characteristic(
            uuid=UUID(0x2A00),
            permissions = ['read', 'write'],
            notify=True,
            value=b'TestDevice'
        ),
    )

if len(sys.argv) < 2:
    print("Usage: python3 ble_peripheral_basic.py <interface>")
    exit()
my_profile = MyPeripheral()
periph = Peripheral(WhadDevice.create(sys.argv[1]), profile=my_profile)

periph.attach_callback(callback=show)

periph.enable_peripheral_mode(adv_data=AdvDataFieldList(
    AdvCompleteLocalName(b'TestMe!'),
    AdvFlagsField()
))

# Sleep 10 seconds and update device name
print('Press a key to update device name')
input()
my_profile.device.device_name.value = b'TestDeviceChanged'
input()
print("Press a key to request pairing")
periph.pairing()
input()
