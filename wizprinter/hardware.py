"""
Central switch for hardware mock mode.

Set WIZPRINTER_MOCK_HARDWARE=1 to make scanner discovery/scanning, printer
discovery, and print jobs return deterministic fake results instead of
touching real SANE/CUPS hardware.

Used by:
  * the pytest suite / CI (no scanner or printer attached to the runner)
  * local development on a machine without the kiosk's hardware
"""
import os

MOCK_HARDWARE: bool = os.environ.get("WIZPRINTER_MOCK_HARDWARE", "0") == "1"
