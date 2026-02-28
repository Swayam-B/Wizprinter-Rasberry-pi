"""WiFi network selection screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty


class WifiScreen(Screen):
    """WiFi network selection with virtual keyboard placeholder."""

    networks = ListProperty([
        {'name': 'WizPrinter_Guest', 'signal': 'strong', 'secured': True},
        {'name': 'Office_WiFi', 'signal': 'strong', 'secured': True},
        {'name': 'Public_Net', 'signal': 'medium', 'secured': False},
        {'name': 'Warehouse_Scanner', 'signal': 'weak', 'secured': False},
    ])

    selected_network = None

    def select_network(self, network_name):
        self.selected_network = network_name
        App.get_running_app().navigate('login')
