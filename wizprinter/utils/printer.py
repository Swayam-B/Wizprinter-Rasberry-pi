import cups
import os

class PrinterManager:
    def __init__(self):
        # The specific name we registered in the terminal
        self.kiosk_printer = "WizPrinter_OfficeJet"
        self.conn = None
        
        try:
            self.conn = cups.Connection()
        except Exception as e:
            print(f"Hardware Error: Could not connect to CUPS: {e}")

    def get_printer_status(self):
        """Checks if the OfficeJet is actually online and idle."""
        if not self.conn:
            return "CUPS_OFFLINE"
        
        printers = self.conn.getPrinters()
        if self.kiosk_printer not in printers:
            return "PRINTER_NOT_FOUND"
        
        # printer-state: 3 (idle), 4 (processing), 5 (stopped/error)
        state = printers[self.kiosk_printer].get('printer-state')
        return state

    def print_document(self, file_path, printer_name=None):
        if not self.conn:
            print("Print failed: No CUPS connection.")
            return False
            
        if not os.path.exists(file_path):
            print(f"Print failed: File not found at {file_path}")
            return False

        # Priority: 1. Manual Override, 2. Our Kiosk Printer, 3. System Default
        dest = printer_name or self.kiosk_printer
        
        # Verify destination exists in current CUPS list
        if dest not in self.conn.getPrinters():
            dest = self.conn.getDefault()

        if not dest:
            print("Print failed: No valid printer destination found.")
            return False

        try:
            # Adding options for a student/academic context (standard letter size)
            options = {
                "media": "na_letter_8.5x11in",
                "fit-to-page": "true",
            }
            
            job_id = self.conn.printFile(dest, file_path, "WizPrinter_Job", options)
            print(f"Job {job_id} sent successfully to {dest}.")
            return True
        except Exception as e:
            print(f"Printing failed: {e}")
            return False