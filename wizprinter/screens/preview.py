"""Document preview screen with Delete/Grade/Print actions."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock


class PreviewScreen(Screen):
    """Document preview with floating action buttons."""

    show_success = BooleanProperty(False)
    page_info = StringProperty('PG 1 / 1')

    def delete_document(self):
        """Delete the current document and go back."""
        App.get_running_app().navigate('documents', direction='right')

    def grade_document(self):
        """Send document for grading."""
        self._show_completion('Grading Complete!')

    def print_document(self):
        """Send document to printer."""
        self._show_completion('Print Sent!')

    def _show_completion(self, message='Task Completed!'):
        """Show success overlay then return to dashboard."""
        self.success_message = message
        self.show_success = True
        Clock.schedule_once(lambda dt: self._finish(), 2.0)

    def _finish(self):
        self.show_success = False
        App.get_running_app().navigate('dashboard')

    def go_back(self):
        App.get_running_app().navigate('documents', direction='right')
