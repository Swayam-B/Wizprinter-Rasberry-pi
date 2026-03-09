from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty
from kivy.clock import Clock

class GradeScreen(Screen):
    page_info = StringProperty('1/1 PAGE')
    show_success = BooleanProperty(False)
    success_message = StringProperty('')
    pages_to_grade = []

    def grade_now(self):
        """Finalizes the document and triggers the grading/printing process."""
        # TODO: Compile PDF and send to Backend API for AI Grading
        # TODO: Optional - print a copy of the graded version via PrinterManager
        self._show_completion('Grading Complete!')

    def _show_completion(self, message='Grading Complete!'):
        """Show success overlay then return to dashboard."""
        self.success_message = message
        self.show_success = True
        Clock.schedule_once(lambda dt: self._finish(), 2.0)

    def _finish(self):
        self.show_success = False
        App.get_running_app().navigate('dashboard')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
