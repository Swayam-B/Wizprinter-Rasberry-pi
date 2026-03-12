import os
import time
import fitz
import subprocess
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import BooleanProperty, StringProperty, ListProperty
from kivy.clock import Clock

class PreviewScreen(Screen):
    page_info = StringProperty('DOC: 0 PGS')

    def load_document(self, doc_name):
        # We don't care about the PDF name anymore. 
        # We just want to trigger the UI to look at the temp folder.
        Clock.schedule_once(self._build_preview, 0.1)

    def _build_preview(self, dt):
        container = self.ids.preview_container
        container.clear_widgets()
        
        temp_dir = 'temp'
        if os.path.exists(temp_dir):
            # Get the JPGs exactly like you did on the Scan screen
            files = sorted([os.path.join(temp_dir, f) for f in os.listdir(temp_dir) if f.endswith('.jpg')])
            self.page_info = f"DOC: {len(files)} PGS"
            
            for path in files:
                # We add them as separate widgets so the GPU never has to load one giant image
                img = KivyImage(
                    source=path,
                    size_hint_y=None,
                    height=container.width * 1.41, 
                    allow_stretch=True,
                    keep_ratio=True
                )
                img.reload()
                container.add_widget(img)

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')

    def delete_document(self):
        # Optional: Add logic to wipe 'temp/' here
        App.get_running_app().navigate('dashboard', direction='right')

    def grade_document(self):
        self.success_message = "GRADING IN PROGRESS..."
        self.show_success = True
        
        Clock.schedule_once(self._execute_print_after_delay, 10.0)
    def _execute_print_after_delay(self, dt):
        """This runs after the 10-second timer."""
        # Change message to printing
        self.success_message = "GRADING COMPLETE! PRINTING..."
        
        # Define the target PDF path
        print_pdf_path = os.path.join(os.getcwd(), "assets", "mocks", "pdf", "graded_oct_24_multiple_page_answered.pdf")
        
        # Execute the Linux print command (lp)
        try:
            if os.path.exists(print_pdf_path):
                # 'lp' sends the file to the default system printer
                subprocess.run(['lp', print_pdf_path], check=True)
                print(f"SENT TO PRINTER: {print_pdf_path}")
            else:
                self.success_message = "ERROR: PDF NOT FOUND"
                print(f"FILE MISSING: {print_pdf_path}")
        except Exception as e:
            self.success_message = "PRINT ERROR"
            print(f"PRINTING FAILED: {e}")

        # 3. Hide the success message and return to dashboard after a short reveal
        Clock.schedule_once(self._finish, 3.0)

    def print_document(self):
        self._show_completion('Print Sent!')

    def _show_completion(self, message):
        self.success_message = message
        self.show_success = True
        Clock.schedule_once(self._finish, 2.0)

    def _finish(self, dt):
        self.show_success = False
        App.get_running_app().navigate('dashboard')
