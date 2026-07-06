"""
WizPrinter Kivy Application
Main application class with screen management and navigation history.
"""

import logging
import os

from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.core.window import Window

from wizprinter.theme import BG_DARK, SCREEN_W, SCREEN_H
from wizprinter.screens.landing      import LandingScreen
from wizprinter.screens.wifi         import WifiScreen
from wizprinter.screens.login        import LoginScreen
from wizprinter.screens.dashboard    import DashboardScreen
from wizprinter.screens.printer_list import PrinterListScreen
from wizprinter.screens.classes      import ClassesScreen
from wizprinter.screens.documents    import DocumentsScreen
from wizprinter.screens.preview      import PreviewScreen
from wizprinter.screens.scan         import ScanScreen
from wizprinter.screens.settings     import SettingsScreen
from wizprinter.widgets.statusbar    import StatusBar
from wizprinter.widgets.bottomnav    import BottomNav

logger = logging.getLogger(__name__)


class WizPrinterApp(App):
    """Main WizPrinter kiosk application."""

    title = 'WizPrinter'

    def build(self):
        Window.size       = (800, 480)
        Window.clearcolor = BG_DARK

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        kv_dir       = os.path.join(project_root, 'kv')

        kv_files = [
            'theme.kv', 'widgets.kv', 'landing.kv', 'wifi.kv', 'login.kv',
            'dashboard.kv', 'printerList.kv', 'classes.kv', 'documents.kv',
            'preview.kv', 'scan.kv', 'settings.kv',
        ]
        for kv_file in kv_files:
            path = os.path.join(kv_dir, kv_file)
            if os.path.exists(path):
                Builder.load_file(path)
                logger.debug("Loaded KV: %s", kv_file)
            else:
                logger.error("KV file not found: %s", path)

        sm = ScreenManager(transition=FadeTransition(duration=0.15))

        try:
            sm.add_widget(LandingScreen(name='landing'))
            sm.add_widget(WifiScreen(name='wifi'))
            sm.add_widget(LoginScreen(name='login'))
            sm.add_widget(DashboardScreen(name='dashboard'))
            sm.add_widget(PrinterListScreen(name='printer_list'))
            sm.add_widget(ClassesScreen(name='classes'))
            sm.add_widget(DocumentsScreen(name='documents'))
            sm.add_widget(PreviewScreen(name='preview'))
            sm.add_widget(ScanScreen(name='scan'))
            sm.add_widget(SettingsScreen(name='settings'))
        except Exception as e:
            logger.critical("Screen init failed: %s", e, exc_info=True)
            raise

        self.selected_printer      = None
        self._printer_list_origin  = 'scan'
        # Navigation history stack — enables true "go back" semantics
        self._nav_stack: list[str] = []

        return sm

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, screen_name: str, direction: str = 'left',
                 origin: str | None = None, push_history: bool = True) -> None:
        """
        Navigate to *screen_name*.

        Pushes the current screen onto the history stack so that go_back()
        always returns to the true previous screen rather than a hardcoded one.
        """
        if screen_name == 'printer_list' and origin:
            self._printer_list_origin = origin

        current = self.root.current
        if push_history and current != screen_name:
            self._nav_stack.append(current)

        self.root.transition = FadeTransition(duration=0.15)
        self.root.current    = screen_name
        logger.debug("Navigate: %s → %s (stack depth %d)",
                     current, screen_name, len(self._nav_stack))

    def go_back(self) -> None:
        """
        Return to the previous screen in the navigation history stack.

        Screens that are always terminal (landing, dashboard) are skipped over
        so the user is never left in an unreachable state.
        """
        # Pop until we find a valid target
        while self._nav_stack:
            target = self._nav_stack.pop()
            if target != self.root.current:
                self.root.transition = FadeTransition(duration=0.15)
                self.root.current    = target
                logger.debug("go_back → %s (stack depth %d)",
                             target, len(self._nav_stack))
                return

        # Stack exhausted — fall back to dashboard (or landing if not logged in)
        from wizprinter.session import session_mgr
        fallback = 'dashboard' if session_mgr.is_valid else 'landing'
        self.root.current = fallback
        logger.debug("go_back stack empty → %s", fallback)
