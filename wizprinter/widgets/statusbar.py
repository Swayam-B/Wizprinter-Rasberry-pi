"""Reusable status bar widget — go_back() uses navigation history stack."""

from kivy.app import App
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout


class StatusBar(BoxLayout):
    title     = StringProperty('WizPrinter')
    hide_home = BooleanProperty(False)
    show_back = BooleanProperty(False)
    show_wifi = BooleanProperty(True)
    back      = ObjectProperty(None)

    def go_back(self):
        """Always delegate to app.go_back() for consistent history-based navigation."""
        App.get_running_app().go_back()
