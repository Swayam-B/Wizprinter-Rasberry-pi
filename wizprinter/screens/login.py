"""Login screen — secure auth, no plaintext credential persistence."""

import logging

import requests
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock

import wizprinter.api_client as api
from wizprinter.session import session_mgr
from wizprinter.accessibility import a11y

logger = logging.getLogger(__name__)


class LoginScreen(Screen):
    password_visible = BooleanProperty(False)
    status_text      = StringProperty("")
    is_loading       = BooleanProperty(False)
    email_focused    = BooleanProperty(False)
    pwd_focused      = BooleanProperty(False)

    def on_enter(self, *args):
        a11y.speak("Login screen. Enter your email and password.")
        # Always clear any leftover text — never leave credentials visible
        self._clear_inputs()
        self.status_text = ""

    def on_leave(self, *args):
        # Wipe inputs whenever the user leaves the login screen
        self._clear_inputs()

    def _clear_inputs(self):
        try:
            self.ids.username_input.text  = ""
            self.ids.password_input.text  = ""
        except Exception:
            pass

    def toggle_password(self):
        self.password_visible = not self.password_visible

    def attempt_login(self, username: str, password: str):
        email = username.strip()
        pwd   = password.strip()

        if not email or not pwd:
            self.status_text = "Enter email and password."
            a11y.speak("Please enter your email and password.")
            return

        self.status_text = "Signing in… first sign-in can take a few minutes."
        self.is_loading  = True
        a11y.speak("Signing in. The first sign-in can take a few minutes, please wait.")

        api.run_in_thread(
            self._do_login,
            email,
            pwd,
            on_success=self._on_login_ok,
            on_error=self._on_login_fail,
        )

    def _do_login(self, email: str, pwd: str):
        """Runs in background thread — never logs credentials."""
        fb = api.firebase_sign_in(email, pwd)

        # Hand token + refresh token to the session manager
        # (never stored anywhere else)
        session_mgr.start(
            id_token      = fb["idToken"],
            refresh_token = fb.get("refreshToken", ""),
            expires_in    = int(fb.get("expiresIn", 3600)),
        )

        # Wire up the session token into api_client headers
        # (api_client reads from session_mgr.token automatically)

        prof = api.onboard_professor()
        api.set_professor_id(prof["id"])
        return prof

    def _on_login_ok(self, prof):
        self.is_loading  = False
        self.status_text = ""
        self._clear_inputs()   # remove credentials from UI immediately
        a11y.speak("Login successful. Welcome to WizPrinter dashboard.")
        App.get_running_app().navigate("dashboard")

    def _on_login_fail(self, exc):
        self.is_loading = False
        api.clear_session()

        msg = str(exc)
        if hasattr(exc, "response") and exc.response is not None:
            try:
                body = exc.response.text or ""
            except Exception:
                body = ""
            msg = f"{msg} {body}"

        is_timeout = (
            isinstance(exc, (requests.Timeout, requests.ConnectionError))
            or "timed out" in msg.lower()
            or "timeout" in msg.lower()
        )

        if "INVALID_LOGIN_CREDENTIALS" in msg or "INVALID_PASSWORD" in msg:
            self.status_text = "Invalid email or password."
            a11y.speak("Login failed. Invalid email or password.")
        elif "EMAIL_NOT_FOUND" in msg:
            self.status_text = "Email not registered."
            a11y.speak("Login failed. That email address is not registered.")
        elif is_timeout:
            # Scale-to-zero backend cold start: the request above just woke it,
            # so a second attempt in a few seconds should be fast.
            self.status_text = "Server is waking up. Tap Sign In again."
            a11y.speak("The server is starting up. Please tap Sign In again in a few seconds.")
        else:
            self.status_text = "Login failed. Check your connection."
            a11y.speak("Login failed. Please check your internet connection.")

        logger.warning("Login failed (non-credential detail): %s",
                       "INVALID_CREDENTIALS" if "INVALID" in msg else type(exc).__name__)

    def go_back(self):
        App.get_running_app().navigate("landing", push_history=False)
