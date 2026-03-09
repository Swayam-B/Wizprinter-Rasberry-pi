from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty
from wizprinter.utils.printer import PrinterManager

class GradeScreen(Screen):
    page_info = StringProperty('1/1 PAGE')
    pages_to_grade = []

    def grade_now(self):
        """Finalizes the document and triggers the grading/printing process."""
        # 1. Compile PDF (Same logic as ScanScreen)
        # 2. Logic to send to your Backend API for AI Grading
        
        # 3. Optional: Print a copy of the graded version
        pm = PrinterManager()
        pm.print_document("graded_report.pdf")
        
        App.get_running_app().navigate('preview')