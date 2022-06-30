from whad.domain.ble import Scanner, Central
from whad.device.uart import UartDevice
from time import time,sleep
from threading import Thread

from whad.helpers import message_filter

"""
scanner = Scanner(UartDevice('/dev/ttyUSB0', 115200))
scanner.start()
while True:
    try:
        for rssi, device in scanner.discover_devices():
            print('%d - %s' % (rssi, device.AdvA))
    except KeyboardInterrupt as exc:
        scanner.stop()
        scanner.device.close()
        break

class MyAsyncScanner(Scanner):
    def __init__(self, device):
        super().__init__(device)

    def on_adv_pdu(self, rssi, packet):
        print('%d - %s' %(
            rssi,
            packet.AdvA
        ))
        
class AsyncScan(Thread):
    def __init__(self, device):
        super().__init__()
        self.scan = MyAsyncScanner(device)

    def run(self):
        self.scan.start()
        while True:
            self.scan.process()
"""

""" Asynchronous scanner
scanner = AsyncScan(UartDevice('/dev/ttyUSB0', 115200))
scanner.start()
scanner.join()
"""

""" Synchronous scanner 
scanner = Scanner(UartDevice('/dev/ttyUSB0', 115200))
scanner.start()
while True:
    try:
        for rssi, device in scanner.discover_devices():
            if (rssi >= -65):
                print('%d - %s' % (rssi, device.AdvA))
    except KeyboardInterrupt as exc:
        scanner.stop()
        break
"""

class deleg(Thread):
    def __init__(self, central):
        super().__init__()
        self.central = central
    
    def run(self):
        sleep(6)
        self.central.send_ctrl_pdu([0x12])


central = Central(UartDevice('/dev/ttyUSB0', 115200))
central.connect_to('D4:3B:04:2C:AD:16')
#central.connect_to('D6:F3:6E:89:DA:F5')
timeout = deleg(central)
central.start()

# Wait for connection
print('... waiting for connection ...')
while not central.connected():
    pass

# Query primary services
print(central.connection)
central.connection.gatt.discover_primary_services()

while True:
    sleep(1)



