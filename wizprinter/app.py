"""
WizPrinter Kivy Application
Main application class with screen management.
"""

import os
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, SlideTransition, NoTransition
from kivy.core.window import Window

from wizprinter.theme import BG_DARK, SCREEN_W, SCREEN_H
from wizprinter.screens.landing import LandingScreen
from wizprinter.screens.wifi import WifiScreen
from wizprinter.screens.login import LoginScreen
from wizprinter.screens.dashboard import DashboardScreen
from wizprinter.screens.classes import ClassesScreen
from wizprinter.screens.documents import DocumentsScreen
from wizprinter.screens.preview import PreviewScreen
from wizprinter.screens.grade import GradeScreen
from wizprinter.screens.scan import ScanScreen
from wizprinter.screens.settings import SettingsScreen


class WizPrinterApp(App):
    """Main WizPrinter kiosk application."""

    title = 'WizPrinter'

    def build(self):
        # Set window properties
        Window.size = (SCREEN_W, SCREEN_H)
        Window.clearcolor = BG_DARK

        # Load all KV layout files
        kv_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'kv')
        kv_files = [
            'theme.kv',
            'widgets.kv',
            'landing.kv',
            'wifi.kv',
            'login.kv',
            'dashboard.kv',
            'classes.kv',
            'documents.kv',
            'preview.kv',
            'grade.kv',
            'scan.kv',
            'settings.kv',
        ]
        for kv_file in kv_files:
            path = os.path.join(kv_dir, kv_file)
            if os.path.exists(path):
                Builder.load_file(path)

        # Create screen manager
        sm = ScreenManager(transition=SlideTransition(duration=0.2))
        sm.add_widget(LandingScreen(name='landing'))
        sm.add_widget(WifiScreen(name='wifi'))
        sm.add_widget(LoginScreen(name='login'))
        sm.add_widget(DashboardScreen(name='dashboard'))
        sm.add_widget(ClassesScreen(name='classes'))
        sm.add_widget(DocumentsScreen(name='documents'))
        sm.add_widget(PreviewScreen(name='preview'))
        sm.add_widget(GradeScreen(name='grade'))
        sm.add_widget(ScanScreen(name='scan'))
        sm.add_widget(SettingsScreen(name='settings'))

        return sm

    def navigate(self, screen_name, direction='left'):
        """Navigate to a screen with transition direction."""
        self.root.transition = SlideTransition(direction=direction, duration=0.2)
        self.root.current = screen_name

    def go_back(self):
        """Navigate back (right slide transition)."""
        self.root.transition = SlideTransition(direction='right', duration=0.2)
        self.root.current = self.root.previous()
