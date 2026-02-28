"""System settings screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App


class SettingsScreen(Screen):
    """Settings: Time/Region, Network Config, Log Out."""

    def open_time_region(self):
        """Open time/region configuration."""
        # TODO: Implement time/region settings
        pass

    def open_network_config(self):
        """Open network configuration."""
        App.get_running_app().navigate('wifi')

    def logout(self):
        """Log out and return to landing screen."""
        App.get_running_app().navigate('landing', direction='right')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
