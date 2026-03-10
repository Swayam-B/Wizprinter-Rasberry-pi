"""Reusable status bar widget for top of screens."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from kivy.app import App

class StatusBar(BoxLayout):
    """Top status bar with optional back button and title."""
    title = StringProperty('WizPrinter')
    hide_home = BooleanProperty(False)
    show_back = BooleanProperty(False)
    show_wifi = BooleanProperty(True)
    
    # ADD THIS LINE to fix the AttributeError
    back = ObjectProperty(None)

    def go_back(self):
        app = App.get_running_app()
        # Explicitly check if we are on the login screen
        if app.root.current == 'login':
            app.root.current = 'landing'
        else:
            app.go_back()
