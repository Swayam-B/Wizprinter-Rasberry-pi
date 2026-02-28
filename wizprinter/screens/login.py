"""User login screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty


class LoginScreen(Screen):
    """Login form with username/password fields."""

    password_visible = BooleanProperty(False)

    def toggle_password(self):
        self.password_visible = not self.password_visible

    def attempt_login(self, username, password):
        """Validate credentials and navigate to dashboard."""
        # TODO: Implement actual authentication against your web backend
        if username and password:
            App.get_running_app().navigate('dashboard')
        else:
            pass  # Show error feedback
