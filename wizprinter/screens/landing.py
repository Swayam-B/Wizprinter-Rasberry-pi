"""Landing / Splash screen - TAP TO START."""

from kivy.uix.screenmanager import Screen
from kivy.app import App


class LandingScreen(Screen):
    """Initial landing screen with WizPrinter branding."""

    def on_tap_start(self):
        App.get_running_app().navigate('wifi')
