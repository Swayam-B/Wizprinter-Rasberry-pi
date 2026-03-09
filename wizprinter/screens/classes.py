"""Class selection screen with semester/subject/class dropdowns."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty


class ClassesScreen(Screen):
    """Semester, Subject, and Class selection dropdowns."""

    semesters = ListProperty(['Fall 2024', 'Spring 2025', 'Summer 2025'])
    subjects = ListProperty(['Computer Science', 'Mathematics', 'Physics', 'Digital Arts'])
    classes = ListProperty([
        'CS101 - Intro to Programming',
        'CS202 - Data Structures',
        'CS303 - UI/UX Design',
    ])

    selected_semester = StringProperty('')
    selected_subject = StringProperty('')
    selected_class = StringProperty('')

    def select_class(self):
        """Confirm class selection and navigate to documents."""
        if (self.selected_semester and self.selected_semester != 'Select Semester' and
            self.selected_subject and self.selected_subject != 'Select Subject' and
            self.selected_class and self.selected_class != 'Select Class'):
            App.get_running_app().navigate('documents')
        else:
            # TODO: Show user feedback that all fields must be selected
            print('Please select semester, subject, and class before continuing.')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
