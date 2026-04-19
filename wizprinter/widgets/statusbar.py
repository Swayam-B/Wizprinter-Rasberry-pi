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
    
    # 1. Matches 'on_back' in login.kv
    back = ObjectProperty(None)
    # 2. Matches 'on_back_release' in settings.kv
    on_back_release = ObjectProperty(None)

    def go_back(self):
        """Standard back navigation logic."""
        app = App.get_running_app()
        # If a specific action was passed via KV, do that first
        if self.back:
            self.back()
        elif self.on_back_release:
            self.on_back_release()
        # Otherwise, use the default app-level back logic
        elif app.root.current == 'login':
            app.root.current = 'landing'
        else:
            # app.go_back() usually defaults to dashboard in your setup
            app.navigate('dashboard', direction='right')

    def on_touch_down(self, touch):
        """
        Kills the touch propagation to prevent it hitting buttons 
        underneath (like SCAN) on the Dashboard.
        """
        if self.collide_point(*touch.pos):
            # If touching the back-button area (left side of status bar)
            if self.show_back and touch.x < (self.x + dp(80)):
                self.go_back()
                return True # This is the "Ghost Touch" fix
        return super().on_touch_down(touch)