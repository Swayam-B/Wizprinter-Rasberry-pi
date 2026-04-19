import os
import shutil
import subprocess
from PIL import Image as PILImage
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import StringProperty, BooleanProperty, ListProperty
from kivy.clock import Clock

from wizprinter.utils.image_file import is_valid_jpeg

class ScanScreen(Screen):
    """Handles multi-page hardware scanning and thumbnail previews."""
    
    page_info = StringProperty('Page 0')
    is_scanning = BooleanProperty(False)
    status_msg = StringProperty("READY TO SCAN")
    # ListProperty triggers on_scanned_images whenever pages are added/removed
    scanned_images = ListProperty([]) 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.temp_dir = "temp"
        os.makedirs(self.temp_dir, exist_ok=True)
        # Auto-find the scanner so e0/e1/e2 doesn't matter
        self.device_path = self._discover_scanner()

    def on_pre_enter(self, *args):
        """Drop corrupt/empty leftovers so Kivy never tries to load them."""
        if not os.path.isdir(self.temp_dir):
            return
        for name in os.listdir(self.temp_dir):
            if not name.lower().endswith((".jpg", ".jpeg")):
                continue
            path = os.path.join(self.temp_dir, name)
            if not is_valid_jpeg(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        # Reconcile list with disk
        self.scanned_images = [
            os.path.abspath(p)
            for p in self.scanned_images
            if is_valid_jpeg(p)
        ]

    def _discover_scanner(self):
        """Automatically finds the active AirScan path for the OfficeJet."""
        try:
            # Runs scanimage -L and captures the text
            result = subprocess.run(['scanimage', '-L'], capture_output=True, text=True)
            for line in result.stdout.splitlines():
                # We look for the airscan line specifically
                if "airscan" in line and "HP OfficeJet" in line:
                    # Extract the string between the backticks ` `
                    import re
                    match = re.search(r"`(.*?)'", line)
                    if match:
                        found_path = match.group(1)
                        print(f"SCANNER FOUND: {found_path}")
                        return found_path
        except Exception as e:
            print(f"Scanner Discovery Error: {e}")
        
        # Fallback to the one we just found if discovery fails
        return "airscan:e0:HP OfficeJet 8020 series [81BDC3]"

    def on_scanned_images(self, instance, value):
        """
        Kivy observer: Automatically clears and repopulates the 
        scrollable thumbnail grid whenever the page list changes.
        """
        if 'thumbnail_grid' not in self.ids:
            return

        grid = self.ids.thumbnail_grid
        grid.clear_widgets()
        
        for img_path in value:
            if not is_valid_jpeg(img_path):
                continue
            abs_path = os.path.abspath(img_path)
            img_widget = KivyImage(
                source=abs_path,
                size_hint_y=None,
                height=grid.width * 1.41,
                allow_stretch=True,
                keep_ratio=True
            )
            img_widget.reload()
            grid.add_widget(img_widget)
        
        Clock.schedule_once(self._scroll_to_bottom, 0.1)

    def _scroll_to_bottom(self, dt):
        if 'scroll_container' in self.ids:
            self.ids.scroll_container.scroll_y = 0

    def add_page(self):
        """Initiates a hardware scan."""
        if self.is_scanning:
            return

        if not shutil.which("scanimage"):
            self.status_msg = "NO SCANNER (install scanimage / SANE)"
            return

        self.is_scanning = True
        self.status_msg = "SCANNING..."
        Clock.schedule_once(self._perform_hardware_scan, 0.2)

    def _perform_hardware_scan(self, dt):
        file_pattern = os.path.join(self.temp_dir, "page_%d.jpg")

        cmd = [
            "scanimage",
            "-d", self.device_path,
            "--source", "ADF",
            "--format=jpeg",
            "--batch=" + file_pattern,
            "--batch-start", str(len(self.scanned_images) + 1),
            "--mode", "Gray",
            "--resolution", "150",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                if "out of paper" in result.stderr.lower():
                    self.status_msg = "ADF EMPTY"
                else:
                    self.status_msg = "SCAN ERROR"
                return

            new_files = sorted([
                os.path.abspath(os.path.join(self.temp_dir, f))
                for f in os.listdir(self.temp_dir)
                if f.startswith("page_") and f.endswith(".jpg")
            ])
            
            self.scanned_images = new_files
            self.page_info = f"Scanned {len(self.scanned_images)} Pages"
            self.status_msg = "READY"

        except Exception as e:
            self.status_msg = "SYSTEM ERROR"
            print(f"Batch Scan Exception: {e}")
        finally:
            self.is_scanning = False

    def delete_page(self):
        """Removes the most recent page from the batch and disk."""
        if self.scanned_images:
            img_to_remove = self.scanned_images.pop()
            if os.path.exists(img_to_remove):
                os.remove(img_to_remove)
            self.page_info = f"Page {len(self.scanned_images)}"
            self.status_msg = "PAGE DELETED"

    def upload(self):
        """Compiles JPG batch into PDF and switches to Preview."""
        if not self.scanned_images:
            self.status_msg = "NO PAGES"
            return

        self.status_msg = "COMPILING..."
        output_name = "latest_scan.pdf"
        scan_pdf_dir = os.path.abspath(os.path.join("temp", "scan_pdf"))
        os.makedirs(scan_pdf_dir, exist_ok=True)
        for old_file in os.listdir(scan_pdf_dir):
            try:
                os.remove(os.path.join(scan_pdf_dir, old_file))
            except: pass
        pdf_path = os.path.join(scan_pdf_dir, output_name)

        try:
            paths = [p for p in self.scanned_images if is_valid_jpeg(p)]
            if not paths:
                self.status_msg = "NO VALID PAGES"
                return
            images = [PILImage.open(f).convert("RGB") for f in paths]
            if images:
                images[0].save(pdf_path, save_all=True, append_images=images[1:])
                self.scanned_images = []

                app = App.get_running_app()
                preview_screen = app.root.get_screen("preview")

                preview_screen.scanned_pdf_path = pdf_path
                preview_screen.show_scan_jpeg_previews()
                app.navigate("preview")

        except Exception as e:
            self.status_msg = "PDF ERROR"
            print(f"PDF Error: {e}")

    def go_back(self):
        """Returns to the dashboard and cleans up temp scans."""
        for img in self.scanned_images:
            if os.path.exists(img):
                os.remove(img)
        self.scanned_images = []
        App.get_running_app().navigate('dashboard', direction='right')
