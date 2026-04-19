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

    on_back_release = ObjectProperty(None)

    def go_back(self):
        """Standard back navigation logic."""
        app = App.get_running_app()
        if app.root.current == 'login':
            app.root.current = 'landing'
        else:
            if self.on_back_release:
                self.on_back_release()
            else:
                app.navigate('dashboard', direction='right')

    def on_touch_down(self, touch):
        """
        Consumes the touch event if it hits the back button area.
        This prevents 'ghost touches' from hitting the Dashboard/Scan buttons.
        """
        if self.collide_point(*touch.pos):
            if self.show_back and touch.x < (self.x + 60):
                self.go_back()
                return True
        return super().on_touch_down(touch)