"""Scan & Upload screen with split view."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty


class ScanScreen(Screen):
    """Split layout: scan preview (left) + action buttons (right)."""

    page_info = StringProperty('Page 1 of 1')

    def add_page(self):
        """Scan another page."""
        # TODO: Trigger physical scanner
        pass

    def delete_page(self):
        """Remove current scanned page."""
        pass

    def upload(self):
        """Upload scanned document to web backend."""
        # TODO: API call to upload service
        App.get_running_app().navigate('preview')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
