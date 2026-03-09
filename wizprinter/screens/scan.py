import os
import subprocess
from PIL import Image
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty
from wizprinter.utils.printer import PrinterManager

class ScanScreen(Screen):
    page_info = StringProperty('Page 1 of 1')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.scanned_images = [] # Initialize list for this instance

    def add_page(self):
        """Triggers the scanner and adds the result to the batch."""
        page_num = len(self.scanned_images) + 1
        filename = f"temp/page_{page_num}.jpg"
        
        os.makedirs('temp', exist_ok=True)

        # Command for Pi Camera Module 3
        cmd = ["libcamera-still", "-o", filename, "--immediate"]
        
        try:
            # Fixed: This must be indented inside the function
            subprocess.run(cmd, check=True)
            self.scanned_images.append(filename)
            self.page_info = f"Page {len(self.scanned_images)} of {len(self.scanned_images)}"
        except Exception as e:
            print(f"Scanner Error: {e}")

    def delete_page(self):
        if self.scanned_images:
            img = self.scanned_images.pop()
            if os.path.exists(img):
                os.remove(img)
            count = len(self.scanned_images)
            self.page_info = f"Page {max(1, count)} of {max(1, count)}"

    def upload(self):
        """Compiles images to PDF and sends to printer via CUPS."""
        if not self.scanned_images:
            return

        pdf_path = "final_scan.pdf"
        
        try:
            images = [Image.open(f).convert('RGB') for f in self.scanned_images]
            # Save multi-page PDF
            images[0].save(pdf_path, save_all=True, append_images=images[1:])

            pm = PrinterManager()
            if pm.print_document(pdf_path):
                # Clean up temp files after successful print
                for img in self.scanned_images:
                    if os.path.exists(img):
                        os.remove(img)
                self.scanned_images = []
                App.get_running_app().navigate('preview')
        except Exception as e:
            print(f"PDF/Print Error: {e}")