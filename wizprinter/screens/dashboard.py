"""Main dashboard with 2x2 action grid."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.clock import Clock
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from datetime import datetime


class DashboardScreen(Screen):
    """Home dashboard with Grade (→ classes), Scan, and Settings."""

    current_time = StringProperty('12:45 PM')
    printer_connected = BooleanProperty(False)
    connected_printer_name = StringProperty('')

    def on_enter(self):
        self._update_time()
        self._clock_event = Clock.schedule_interval(lambda dt: self._update_time(), 30)

    def on_leave(self):
        if hasattr(self, '_clock_event'):
            self._clock_event.cancel()

    def _update_time(self):
        self.current_time = datetime.now().strftime('%I:%M %p')

    def set_printer(self, printer_name):
        """Called by PrinterListScreen when the user selects a printer."""
        self.connected_printer_name = printer_name
        self.printer_connected = bool(printer_name)

    def nav_scan(self):
        app = App.get_running_app()
        app._printer_list_origin = 'scan'
        app.navigate('printer_list')

    def nav_classes(self):
        app = App.get_running_app()
        app._printer_list_origin = 'grade'
        app.navigate('printer_list')

    def nav_settings(self):
        App.get_running_app().navigate('settings')