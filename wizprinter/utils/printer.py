import cups
import os

class PrinterManager:
    def __init__(self):
        # Established connection to the local CUPS server
        try:
            self.conn = cups.Connection()
        except Exception as e:
            print(f"Hardware Error: Could not connect to CUPS: {e}")
            self.conn = None

    def print_document(self, file_path, printer_name=None):
        if not self.conn:
            return False
            
        if not os.path.exists(file_path):
            return False

        # Fallback to default printer if none provided
        dest = printer_name or self.conn.getDefault()
        
        try:
            job_id = self.conn.printFile(dest, file_path, "WizPrinter_Job", {})
            print(f"Job {job_id} sent successfully.")
            return True
        except Exception as e:
            print(f"Printing failed: {e}")
            return False