"""
Thin CUPS wrapper for one-shot document printing.

`PrinterManager` connects to the local CUPS server (unless WIZPRINTER_MOCK_HARDWARE
is set, in which case it no-ops with fake success) and exposes `print_document()`,
which validates the file and destination before submitting a job. The `cups`
import is guarded so the module stays importable on non-Pi dev machines and CI.

Note: the live grading/print flow uses GradingStatusMixin.send_to_printer for
its retry/queue behaviour; this class is the simpler standalone helper (and is
exercised by tests/test_hardware_mock.py).
"""
import logging
import os

from wizprinter.hardware import MOCK_HARDWARE

try:
    import cups
except ImportError:
    cups = None

logger = logging.getLogger(__name__)


class PrinterManager:
    def __init__(self):
        self.conn = None
        if MOCK_HARDWARE:
            logger.info("Mock hardware mode — skipping CUPS connection.")
            return
        if cups is None:
            logger.error("pycups not installed; printing unavailable.")
            return
        try:
            self.conn = cups.Connection()
        except Exception as e:
            logger.error("Could not connect to CUPS: %s", e)

    def print_document(self, file_path, printer_name=None):
        if MOCK_HARDWARE:
            logger.info("Mock print job: %s -> %s", file_path, printer_name or "default")
            return True

        if not self.conn:
            logger.error("Print failed: no CUPS connection.")
            return False

        if not os.path.exists(file_path):
            logger.error("Print failed: file not found at %s", file_path)
            return False

        # Use the printer selected by the user, or fall back to CUPS default
        dest = printer_name or self.conn.getDefault()

        if not dest or dest not in self.conn.getPrinters():
            logger.error("Print failed: no valid printer destination found.")
            return False

        try:
            options = {
                "media": "na_letter_8.5x11in",
                "scaling": "100",
            }
            job_id = self.conn.printFile(dest, file_path, "WizPrinter_Job", options)
            logger.info("Job %s sent to %s.", job_id, dest)
            return True
        except Exception as e:
            logger.error("Printing failed: %s", e)
            return False
