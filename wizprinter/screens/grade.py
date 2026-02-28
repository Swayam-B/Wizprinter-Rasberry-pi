"""Grade document screen with split view."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty


class GradeScreen(Screen):
    """Split layout: PDF preview (left) + action buttons (right)."""

    page_info = StringProperty('1/1 PAGE')

    def add_page(self):
        """Add another page to grade batch."""
        # TODO: Trigger scanner or file picker
        pass

    def delete_page(self):
        """Remove current page from batch."""
        pass

    def grade_now(self):
        """Submit document for AI grading via web backend."""
        # TODO: API call to your grading web service
        App.get_running_app().navigate('preview')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
