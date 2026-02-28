"""Reusable bottom navigation bar widget."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty
from kivy.app import App


class BottomNav(BoxLayout):
    """Bottom navigation with Home, Docs, Scan, Settings tabs."""
    active_tab = StringProperty('home')

    def navigate(self, tab_name):
        self.active_tab = tab_name
        screen_map = {
            'home': 'dashboard',
            'docs': 'documents',
            'scan': 'scan',
            'settings': 'settings',
        }
        target = screen_map.get(tab_name, 'dashboard')
        App.get_running_app().navigate(target)
