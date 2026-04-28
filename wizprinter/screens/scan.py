import os
import subprocess
from PIL import Image as PILImage
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import StringProperty, BooleanProperty, ListProperty
from kivy.clock import Clock

class ScanScreen(Screen):
    """Handles multi-page hardware scanning and thumbnail previews."""
    
    page_info = StringProperty('Page 0')
    is_scanning = BooleanProperty(False)
    status_msg = StringProperty("READY TO SCAN")
    # ListProperty triggers on_scanned_images whenever pages are added/removed
    scanned_images = ListProperty([]) 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.temp_dir = 'temp'
        os.makedirs(self.temp_dir, exist_ok=True)
        # Auto-find the scanner so e0/e1/e2 doesn't matter
        self.device_path = self._discover_scanner()

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
            # Create a thumbnail widget for each scanned page
            img_widget = KivyImage(
                source=img_path,
                size_hint_y=None,
                # Maintain A4/Letter aspect ratio for the thumbnail
                height=grid.width * 1.41,
                allow_stretch=True,
                keep_ratio=True
            )
            # Ensure Kivy doesn't show a cached version of the file
            img_widget.reload()
            grid.add_widget(img_widget)
        
        # Scroll to the bottom to show the most recent scan
        Clock.schedule_once(self._scroll_to_bottom, 0.1)

    def _scroll_to_bottom(self, dt):
        if 'scroll_container' in self.ids:
            self.ids.scroll_container.scroll_y = 0

    def add_page(self):
        """Initiates a hardware scan."""
        if self.is_scanning:
            return

        self.is_scanning = True
        self.status_msg = "SCANNING..."
        # Delay allows the UI to show the 'Scanning' status before hardware block
        Clock.schedule_once(self._perform_hardware_scan, 0.2)
    def _perform_hardware_scan(self, dt):
        # --- FIXED INDENTATION BLOCK ---
        page_num = len(self.scanned_images) + 1
        filename = os.path.join(self.temp_dir, f"page_{page_num}.jpg")

        # Command optimized for speed (150 DPI) and hardware compatibility
        cmd = [
            "scanimage",
            "-d", self.device_path,
            "--format=jpeg",
            "--mode", "Gray",
            "--resolution", "150" 
        ]
        
        try:
            with open(filename, 'wb') as f:
                result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
            
            if result.returncode == 0:
                # Appending to the ListProperty triggers the 'on_scanned_images' UI update
                self.scanned_images.append(filename)
                self.page_info = f"Page {len(self.scanned_images)}"
                self.status_msg = "READY"
            else:
                self.status_msg = "SCAN ERROR"
                print(f"SANE Error: {result.stderr}")
                
        except Exception as e:
            self.status_msg = "SYSTEM ERROR"
            print(f"Subprocess Exception: {e}")
        
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
        """Compiles JPG batch into high-res PDF and switches to Preview."""
        if not self.scanned_images:
            self.status_msg = "NO PAGES"
            return

        self.status_msg = "COMPILING..."
        output_name = 'latest_scan.pdf'
        pdf_path = os.path.join('assets', 'mocks', 'pdf', output_name)
        
        try:
            # Use Pillow to wrap the JPGs into a multi-page PDF
            images = [PILImage.open(f).convert('RGB') for f in self.scanned_images]
            if images:
                images[0].save(
                    pdf_path, 
                    save_all=True, 
                    append_images=images[1:]
                )

                # Cleanup temp files
#                for img in self.scanned_images:
#                    if os.path.exists(img):
#                        os.remove(img)
                self.scanned_images = []
                
                # Hand off to PreviewScreen
                app = App.get_running_app()
                preview_screen = app.root.get_screen('preview')
        
                # Load the images into preview BEFORE navigating
                preview_screen.load_document('latest_scan.pdf')
        
                # Navigate using your app's helper
                app.navigate('preview')
                
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
