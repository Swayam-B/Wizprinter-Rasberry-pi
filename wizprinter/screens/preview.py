"""Document preview screen with Delete/Grade/Print actions."""

import os
import fitz  # PyMuPDF
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock

class PreviewScreen(Screen):
    """Document preview with floating action buttons."""

    # These properties MUST be defined here to stop the KV AttributeErrors
    show_success = BooleanProperty(False)
    # Setting this to empty stops the logo from appearing by default
    current_page_source = StringProperty('') 
    page_info = StringProperty('PG 1 / 1')
    success_message = StringProperty('Task Completed!')

    def load_document(self, doc_name):
        """Converts PDF to image and updates the UI."""
        pdf_path = os.path.join('assets', 'mocks', 'pdf', doc_name)
        target_dir = os.path.join('assets', 'mocks', 'pdf')
        temp_path = os.path.join(target_dir, 'temp_preview.png')

        if not os.path.exists(pdf_path):
            print(f"File not found: {pdf_path}")
            return

        try:
            doc = fitz.open(pdf_path)
            self.page_info = f"PG 1 / {len(doc)}"
            page = doc.load_page(0)
            
            # Reduce margin to 20 so we don't cut off question numbers
            margin = 20 
            full_rect = page.rect
            crop_rect = fitz.Rect(
                full_rect.x0 + margin, 
                full_rect.y0 + margin, 
                full_rect.x1 - margin, 
                full_rect.y1 - margin
            )
            
            # Render at 4x scale for crispness when zoomed
            pix = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=crop_rect)
            pix.save(temp_path)
            doc.close()

            self.current_page_source = temp_path
            # Reset scroll to top
            if 'scroll_container' in self.ids:
                self.ids.scroll_container.scroll_y = 1.0
                # Reset horizontal scroll to center
                self.ids.scroll_container.scroll_x = 0.5

            # Update KV properties
            self.current_page_source = temp_path
            
            # Reset scroll to top
            if 'scroll_container' in self.ids:
                self.ids.scroll_container.scroll_y = 1.0
            
            # Force Kivy to reload the image from disk
            if 'preview_image' in self.ids:
                self.ids.preview_image.reload()

        except Exception as e:
            print(f"Error rendering PDF: {e}")

    def go_back(self):
        """Return to the document selection list."""
        App.get_running_app().navigate('documents', direction='right')

    def delete_document(self):
        App.get_running_app().navigate('documents', direction='right')

    def grade_document(self):
        self._show_completion('Grading Complete!')

    def print_document(self):
        self._show_completion('Print Sent!')

    def _show_completion(self, message='Task Completed!'):
        self.success_message = message
        self.show_success = True
        Clock.schedule_once(self._finish, 2.0)

    def _finish(self, dt):
        self.show_success = False
        App.get_running_app().navigate('dashboard')
