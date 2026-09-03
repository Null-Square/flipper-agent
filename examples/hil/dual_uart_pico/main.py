"""Deterministic dual-path UART HIL fixture for an RP2040 Pico/Pico W.

Copy this file to an owned RP2040 board as ``main.py`` after installing
MicroPython. It emits the same marker over the USB CDC console and UART1 TX
(GP4) so one physical fixture can exercise both host.local serial assessment
and Flipper-side UART observation.
"""

import time

from machine import UART, Pin

BANNER = "NULLSQUARE-HIL-READY"
BAUDRATE = 115200
UART_ID = 1
UART_TX_GPIO = 4
UART_RX_GPIO = 5
INTERVAL_MS = 100

uart = UART(
    UART_ID,
    baudrate=BAUDRATE,
    bits=8,
    parity=None,
    stop=1,
    tx=Pin(UART_TX_GPIO),
    rx=Pin(UART_RX_GPIO),
)

payload = (BANNER + "\r\n").encode("ascii")
time.sleep_ms(500)

while True:
    # MicroPython stdout is the Pico USB CDC console used by the host-provider HIL path.
    print(BANNER)
    # Only TX is required by the Flipper observation path; GP5/RX remains unconnected.
    uart.write(payload)
    time.sleep_ms(INTERVAL_MS)
