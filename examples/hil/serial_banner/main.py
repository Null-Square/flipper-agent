# Deterministic target fixture for Hardware Pentest Agent serial HIL.
#
# Copy this as main.py to an owned MicroPython development board whose
# console is exposed to the host over USB serial.

import time

BANNER = "NULLSQUARE-HIL-READY"
INTERVAL_MS = 100

while True:
    print(BANNER)
    time.sleep_ms(INTERVAL_MS)
