"""Document list screen."""

from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty


class DocumentsScreen(Screen):
    """Scrollable list of available documents."""

    documents = ListProperty([
        {'name': 'Resume_Final.pdf', 'size': '1.2 MB', 'type': 'PDF Document', 'icon': 'picture_as_pdf'},
        {'name': 'Boarding_Pass.png', 'size': '450 KB', 'type': 'PNG Image', 'icon': 'image'},
        {'name': 'Contract_Draft.docx', 'size': '2.1 MB', 'type': 'Word Doc', 'icon': 'description'},
        {'name': 'Photo_ID.jpg', 'size': '890 KB', 'type': 'JPEG Image', 'icon': 'photo_camera'},
        {'name': 'Notes_Meeting.txt', 'size': '12 KB', 'type': 'Text File', 'icon': 'text_snippet'},
    ])

    def select_document(self, doc_name):
        """Select a document and navigate to preview."""
        # TODO: Pass selected document data to preview screen
        App.get_running_app().navigate('preview')

    def go_back(self):
        App.get_running_app().navigate('classes', direction='right')
