"""Main dashboard with 2x2 action grid."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty
from datetime import datetime


class DashboardScreen(Screen):
    """Home dashboard with Grade, Scan, Classes, Settings buttons."""

    current_time = StringProperty('12:45 PM')

    def on_enter(self):
        self._update_time()
        self._clock_event = Clock.schedule_interval(lambda dt: self._update_time(), 30)

    def on_leave(self):
        if hasattr(self, '_clock_event'):
            self._clock_event.cancel()

    def _update_time(self):
        self.current_time = datetime.now().strftime('%I:%M %p')

    def nav_grade(self):
        App.get_running_app().navigate('grade')

    def nav_scan(self):
        App.get_running_app().navigate('scan')

    def nav_classes(self):
        App.get_running_app().navigate('classes')

    def nav_settings(self):
        App.get_running_app().navigate('settings')
