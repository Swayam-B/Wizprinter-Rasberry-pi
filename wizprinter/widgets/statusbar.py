"""Reusable status bar widget — go_back() uses navigation history stack."""

from kivy.app import App
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout


class StatusBar(BoxLayout):
    title     = StringProperty('WizPrinter')
    hide_home = BooleanProperty(False)
    show_back = BooleanProperty(False)
    show_wifi = BooleanProperty(True)
    back      = ObjectProperty(None)

    def on_kv_post(self, base_widget):
        # Give the icon-only left button a spoken label for explore-by-touch.
        self._sync_nav_label()
        self.bind(show_back=lambda *a: self._sync_nav_label(),
                  hide_home=lambda *a: self._sync_nav_label())

    def _sync_nav_label(self):
        btn = self.ids.get('nav_btn')
        if btn is None:
            return
        if self.show_back:
            btn.a11y_label = 'Back'
        elif not self.hide_home:
            btn.a11y_label = 'Home'
        else:
            btn.a11y_label = ''

    def go_back(self):
        """Always delegate to app.go_back() for consistent history-based navigation."""
        App.get_running_app().go_back()
