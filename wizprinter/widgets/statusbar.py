"""Reusable status bar widget for top of screens."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty
from kivy.app import App


class StatusBar(BoxLayout):
    """Top status bar with optional back button and title."""
    title = StringProperty('WizPrinter')
    show_back = BooleanProperty(False)
    show_wifi = BooleanProperty(True)

    def go_back(self):
        App.get_running_app().go_back()
