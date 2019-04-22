import pyb
import machine
import sys
import micropython

import time
import json

import uasyncio as asyncio

# upytester module(s)
from upyt.utils import external_interrupt
from upyt.cmd import interpret, set_serial_port
import upyt.sched


# Allocate memory for callback debugging
micropython.alloc_emergency_exception_buf(100)

def _startup_flash():
    # Flash onboard LEDs in sequence
    for i in [4, 3, 2, 1, 2, 3, 4]:
        pyb.LED(i).on()
        time.sleep(0.05)
        pyb.LED(i).off()

_startup_flash()

vcp = pyb.USB_VCP()
set_serial_port(vcp)

def process_line(line):
    # Receive & decode data
    try:
        obj = json.loads(line)
    except ValueError:
        # If invalid JSON is received from host, ignore it.
        # why?: I've been receiving "AT" commands from an ubuntu service.
        # ref: https://stackoverflow.com/questions/31774566
        # assumption:
        #   These spurious characters will not be injected in the
        #   middle of a command.
        # TODO: Check what process is using the serial port.
        return

    # Interpret command, then respond with 'ok'
    #   Order is imporant:
    #       The host's transmit() method will block until it receives an 'ok'.
    #       With the interpret/response in this order, any exception raised
    #       while interpreting the object will cause the transmit() method
    #       to fail, causing the test itself to fail.
    #   Trade-off:
    #       This makes communication slightly slower, because the command has
    #       to complete before the host can begin to process the next command.
    #       However, it does enable tests to... you know... fail when they
    #       should. So the choice seems like a no-brainer.
    interpret(obj)
    vcp.write(b'ok\r')

async def listener():
    """
    Reads lines from Virtual Comm Port (VCP) and send them to be
    processed.
    """
    # TODO: create a global buffer, and populate via memoryview
    line = b''

    # Stop mainloop on 'USR' button press
    while upyt.sched.keepalive:
        c = vcp.recv(1, timeout=0)  # non-blocking
        if c:
            if c == b'\r':
                process_line(line)
                line = b''
            else:
                line += c
        else:
            await asyncio.sleep_ms(1)

upyt.sched.init_loop()  # initialize asyncio loop object

# Bench Libraries
#   note: imported after scheduler loop initialised, just incase somebody has
#         used "from sched import loop" in a custom lib
sys.path.append('/sd/lib_bench')
sys.path.append('/flash/lib_bench')
try:
    import bench
except ImportError as e:
    if "'bench'" not in e.args[0]:
        # import error was not from a nested library fault
        raise
    pass  # else: fail quietly

# Main loop
try:
    # start asyncio.get_event_loop()
    upyt.sched.loop.run_until_complete(listener())
except Exception as e:
    with open('/sd/exception.txt', 'w') as fh:
        fh.write(repr(e))
    raise

# after mainloop, flash LED, close serial over USB.
#   (end of mainloop will open a repl for debugging)
pyb.LED(2).on()
time.sleep(0.05)
pyb.LED(2).off()
