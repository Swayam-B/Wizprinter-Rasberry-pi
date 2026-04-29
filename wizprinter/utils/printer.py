import cups
import os

class PrinterManager:
    def __init__(self):
        self.conn = None
        try:
            self.conn = cups.Connection()
        except Exception as e:
            print(f"Hardware Error: Could not connect to CUPS: {e}")

    def print_document(self, file_path, printer_name=None):
        if not self.conn:
            print("Print failed: No CUPS connection.")
            return False

        if not os.path.exists(file_path):
            print(f"Print failed: File not found at {file_path}")
            return False

        # Use the printer selected by the user, or fall back to CUPS default
        dest = printer_name or self.conn.getDefault()

        if not dest or dest not in self.conn.getPrinters():
            print("Print failed: No valid printer destination found.")
            return False

        try:
            options = {
                "media": "na_letter_8.5x11in",
                "scaling": "100",
                # "fit-to-page": "true",
            }
            job_id = self.conn.printFile(dest, file_path, "WizPrinter_Job", options)
            print(f"Job {job_id} sent successfully to {dest}.")
            return True
        except Exception as e:
            print(f"Printing failed: {e}")
            return False