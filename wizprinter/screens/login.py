"""User login screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty

import wizprinter.api_client as api


class LoginScreen(Screen):
    password_visible = BooleanProperty(False)
    status_text = StringProperty("")

    def toggle_password(self):
        self.password_visible = not self.password_visible

    def attempt_login(self, username, password):
        email = username.strip()
        pwd = password.strip()
        if not email or not pwd:
            self.status_text = "Enter email and password."
            return
        self.status_text = "Signing in..."
        api.run_in_thread(
            self._do_login,
            email,
            pwd,
            on_success=self._on_login_ok,
            on_error=self._on_login_fail,
        )

    def _do_login(self, email, pwd):
        fb = api.firebase_sign_in(email, pwd)
        api.set_token(fb["idToken"])
        prof = api.onboard_professor()
        api.set_professor_id(prof["id"])
        return prof

    def _on_login_ok(self, prof):
        self.status_text = ""
        App.get_running_app().navigate("dashboard")

"""User login screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty

import wizprinter.api_client as api


class LoginScreen(Screen):
    password_visible = BooleanProperty(False)
    status_text = StringProperty("")

    def toggle_password(self):
        self.password_visible = not self.password_visible

    def attempt_login(self, username, password):
        email = username.strip()
        pwd = password.strip()
        if not email or not pwd:
            self.status_text = "Enter email and password."
            return
        self.status_text = "Signing in..."
        api.run_in_thread(
            self._do_login,
            email,
            pwd,
            on_success=self._on_login_ok,
            on_error=self._on_login_fail,
        )

    def _do_login(self, email, pwd):
        fb = api.firebase_sign_in(email, pwd)
        api.set_token(fb["idToken"])
        prof = api.onboard_professor()
        api.set_professor_id(prof["id"])
        return prof

    def _on_login_ok(self, prof):
        self.status_text = ""
        App.get_running_app().navigate("dashboard")

    def _on_login_fail(self, exc):
        api.clear_session()
        msg = str(exc)
        if hasattr(exc, "response") and exc.response is not None:
            try:
                body = exc.response.text or ""
            except Exception:
                body = ""
            msg = f"{msg} {body}"
        if "INVALID_LOGIN_CREDENTIALS" in msg or "INVALID_PASSWORD" in msg:
            self.status_text = "Invalid email or password."
        elif "EMAIL_NOT_FOUND" in msg:
            self.status_text = "Email not registered."
        else:
            self.status_text = "Login failed. Check connection."