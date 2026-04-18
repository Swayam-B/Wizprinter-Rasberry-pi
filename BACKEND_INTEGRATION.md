# WizPrinter Pi — Backend Integration Plan

## Overview

This document is a self-contained implementation plan for wiring the Pi kiosk to the live WizPrinter backend (FastAPI on Azure). Every screen currently uses hardcoded/mock data. This plan replaces all of that with real API calls.

**Pi repo:** `/Users/srikarpunna/Documents/Wizprinter-Rasberry-pi`  
**Backend repo:** `/Users/srikarpunna/Documents/WizPrinter-Backend-`  
**UI repo (reference):** `/Users/srikarpunna/Documents/Wiz-printer-UI`

Do not touch anything inside `.venv/`.

---

## Auth Model

Every backend endpoint requires:
```
Authorization: Bearer <firebase_id_token>
```

Firebase ID tokens come from the **Firebase REST Auth API** (not the backend):
```
POST https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=<FIREBASE_API_KEY>
Content-Type: application/json
Body: { "email": "...", "password": "...", "returnSecureToken": true }
Response: { "idToken": "...", "refreshToken": "...", "expiresIn": "3600" }
```

After getting the `idToken`, call the backend to create/fetch the professor record:
```
POST /api/professors/onboard
Authorization: Bearer <idToken>
Response: { "id": "<uuid>", "email": "...", "name": "...", "credits": N }
```

Store `idToken` and `professor_id` in a module-level singleton for the session. Clear on logout.

---

## Data Hierarchy

```
Semester
  └─ Subject  (a course the professor teaches)
       ├─ Class   (a student group, e.g. "Section A")
       └─ Exam    (question paper + master key — these are the "documents")
            └─ Grading Session  (one per student PDF uploaded)
```

The Pi Classes screen = Semester → Subject → Class (three dropdowns).  
The Pi Documents screen = Exams for the selected Subject.  
The Pi Grade flow = upload scanned PDF → poll → download graded PDF → print.

---

## Grading Flow (use this, not `/api/grade-paper`)

The UI has two grading paths. The Pi must use **only the exam-based flow**:

```
POST /api/exams/{exam_id}/grade
  form field: class_id = <uuid>
  form file:  file = <scanned PDF, field name is "file">

Single PDF response:  { "session_id": "...", "status": "processing", "batch_id": "..." }
Batch PDF response:   { "batch_id": "...", "count": N, "sessions": [...] }

Poll single: GET /api/sessions/{session_id}
Poll batch:  GET /api/batches/{batch_id}

Session statuses: started → uploaded → processing → completed / failed

When completed: response contains "graded_url" (Azure SAS URL, time-limited, no auth header needed to download)
```

Do NOT use `POST /api/grade-paper`. That is a separate "quick grade" feature for the web UI only.

---

## Environment Setup

Add to `.env` at the repo root (create if missing):
```
WIZPRINTER_API_URL=https://<your-azure-backend-url>
FIREBASE_API_KEY=<your-firebase-web-api-key>
```

At the top of `main.py`, add:
```python
from dotenv import load_dotenv
load_dotenv()
```

`python-dotenv` is already in `requirements.txt`. If it isn't, add it.

---

## Step 1 — Create `wizprinter/api_client.py` (new file)

Shared HTTP layer. All screens import from here. All blocking network calls must run in a background thread using `run_in_thread()` so they don't freeze the Kivy UI.

```python
"""Shared API client for WizPrinter Pi."""
import os
import threading
import requests

# ── Session state (in-memory, cleared on logout) ──────────────────────────────
_token: str = ""
_professor_id: str = ""
_selected_semester_id: str = ""
_selected_subject_id: str = ""
_selected_class_id: str = ""
_selected_exam_id: str = ""

BASE_URL = os.environ.get("WIZPRINTER_API_URL", "http://localhost:8000")
FIREBASE_API_KEY = os.environ.get("FIREBASE_API_KEY", "")


def set_token(token: str):
    global _token
    _token = token

def get_token() -> str:
    return _token

def set_professor_id(pid: str):
    global _professor_id
    _professor_id = pid

def get_professor_id() -> str:
    return _professor_id

def set_selection(semester_id="", subject_id="", class_id="", exam_id=""):
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    if semester_id: _selected_semester_id = semester_id
    if subject_id:  _selected_subject_id  = subject_id
    if class_id:    _selected_class_id    = class_id
    if exam_id:     _selected_exam_id     = exam_id

def get_selection():
    return {
        "semester_id": _selected_semester_id,
        "subject_id":  _selected_subject_id,
        "class_id":    _selected_class_id,
        "exam_id":     _selected_exam_id,
    }

def clear_session():
    global _token, _professor_id
    global _selected_semester_id, _selected_subject_id, _selected_class_id, _selected_exam_id
    _token = _professor_id = ""
    _selected_semester_id = _selected_subject_id = _selected_class_id = _selected_exam_id = ""


def _headers():
    return {"Authorization": f"Bearer {_token}"}


def firebase_sign_in(email: str, password: str) -> dict:
    """Returns Firebase JSON (idToken, refreshToken) or raises on failure."""
    url = (
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
        f"?key={FIREBASE_API_KEY}"
    )
    resp = requests.post(
        url,
        json={"email": email, "password": password, "returnSecureToken": True},
        timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def onboard_professor() -> dict:
    """POST /api/professors/onboard — call after firebase_sign_in."""
    resp = requests.post(f"{BASE_URL}/api/professors/onboard", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_semesters() -> list:
    """GET /api/semesters"""
    resp = requests.get(f"{BASE_URL}/api/semesters", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_subjects(semester_id: str) -> list:
    """GET /api/subjects?semester_id=<uuid>"""
    resp = requests.get(
        f"{BASE_URL}/api/subjects",
        headers=_headers(),
        params={"semester_id": semester_id},
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def get_classes(subject_id: str) -> list:
    """GET /api/classes/by-subject/<uuid>"""
    resp = requests.get(
        f"{BASE_URL}/api/classes/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def get_exams(subject_id: str) -> list:
    """GET /api/exams/by-subject/<uuid>"""
    resp = requests.get(
        f"{BASE_URL}/api/exams/by-subject/{subject_id}",
        headers=_headers(),
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def submit_grading_session(exam_id: str, class_id: str, pdf_path: str) -> dict:
    """
    POST /api/exams/{exam_id}/grade
    Multipart: class_id (form field), file (PDF, field name must be 'file').
    Returns { batch_id, count, sessions[] } for batch
         or { session_id, status, batch_id } for single.
    """
    with open(pdf_path, "rb") as f:
        resp = requests.post(
            f"{BASE_URL}/api/exams/{exam_id}/grade",
            headers=_headers(),
            data={"class_id": class_id},
            files={"file": (os.path.basename(pdf_path), f, "application/pdf")},
            timeout=60
        )
    resp.raise_for_status()
    return resp.json()


def get_batch_status(batch_id: str) -> dict:
    """GET /api/batches/{batch_id}"""
    resp = requests.get(f"{BASE_URL}/api/batches/{batch_id}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_session_status(session_id: str) -> dict:
    """GET /api/sessions/{session_id}"""
    resp = requests.get(f"{BASE_URL}/api/sessions/{session_id}", headers=_headers(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def download_graded_pdf(url: str, dest_path: str):
    """Download SAS URL to a local file. No auth header — URL is self-authenticating."""
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)


def run_in_thread(fn, *args, on_success=None, on_error=None):
    """
    Run fn(*args) in a daemon thread.
    on_success(result) and on_error(exc) are called back on the Kivy main thread.
    """
    from kivy.clock import Clock

    def _run():
        try:
            result = fn(*args)
            if on_success:
                Clock.schedule_once(lambda dt: on_success(result), 0)
        except Exception as e:
            if on_error:
                Clock.schedule_once(lambda dt: on_error(e), 0)

    threading.Thread(target=_run, daemon=True).start()
```

---

## Step 2 — Replace `wizprinter/screens/login.py`

**What currently exists:** `attempt_login()` accepts any non-empty string and navigates to dashboard. No API call.

**What to replace it with:**

```python
"""User login screen."""
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import BooleanProperty, StringProperty
import wizprinter.api_client as api


class LoginScreen(Screen):
    password_visible = BooleanProperty(False)
    status_text = StringProperty('')

    def toggle_password(self):
        self.password_visible = not self.password_visible

    def attempt_login(self, username, password):
        email = username.strip()
        pwd = password.strip()
        if not email or not pwd:
            self.status_text = 'Enter email and password.'
            return
        self.status_text = 'Signing in...'
        api.run_in_thread(
            self._do_login, email, pwd,
            on_success=self._on_login_ok,
            on_error=self._on_login_fail
        )

    def _do_login(self, email, pwd):
        fb = api.firebase_sign_in(email, pwd)
        api.set_token(fb['idToken'])
        prof = api.onboard_professor()
        api.set_professor_id(prof['id'])
        return prof

    def _on_login_ok(self, prof):
        self.status_text = ''
        App.get_running_app().navigate('dashboard')

    def _on_login_fail(self, exc):
        api.clear_session()
        msg = str(exc)
        if 'INVALID_LOGIN_CREDENTIALS' in msg or 'INVALID_PASSWORD' in msg:
            self.status_text = 'Invalid email or password.'
        elif 'EMAIL_NOT_FOUND' in msg:
            self.status_text = 'Email not registered.'
        else:
            self.status_text = 'Login failed. Check connection.'
```

**KV change required — `kv/login.kv`:**  
Add this label just above the Login button (inside the form `BoxLayout`):
```kv
Label:
    text: root.status_text
    font_size: '12sp'
    color: 1, 0.3, 0.3, 1
    size_hint_y: None
    height: '20dp'
    text_size: self.size
    halign: 'center'
```

---

## Step 3 — Replace `wizprinter/screens/classes.py`

**What currently exists:** Three hardcoded `ListProperty` lists (semesters, subjects, classes). No API calls.

**Key constraint from KV:** The Spinners bind `values: root.semesters`, `values: root.subjects`, `values: root.classes` — these must stay as `ListProperty` of display-name strings. Maintain separate `_id` dicts internally to look up the UUID when a name is selected.

**What to replace it with:**

```python
"""Class selection screen — Semester / Subject / Class dropdowns."""
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import ListProperty, StringProperty
import wizprinter.api_client as api


class ClassesScreen(Screen):
    semesters = ListProperty([])
    subjects  = ListProperty([])
    classes   = ListProperty([])

    selected_semester = StringProperty('')
    selected_subject  = StringProperty('')
    selected_class    = StringProperty('')

    # Internal maps: display name -> UUID
    _semester_ids = {}
    _subject_ids  = {}
    _class_ids    = {}

    def on_enter(self):
        self.semesters = ['Loading...']
        self.subjects  = []
        self.classes   = []
        api.run_in_thread(
            api.get_semesters,
            on_success=self._on_semesters,
            on_error=lambda e: self._set_error('semesters', e)
        )

    def _on_semesters(self, data):
        self._semester_ids = {s['name']: s['id'] for s in data}
        self.semesters = list(self._semester_ids.keys()) if data else ['No semesters found']

    def on_selected_semester(self, instance, value):
        sid = self._semester_ids.get(value)
        if not sid:
            return
        api.set_selection(semester_id=sid)
        self.subjects = ['Loading...']
        self.classes  = []
        api.run_in_thread(
            api.get_subjects, sid,
            on_success=self._on_subjects,
            on_error=lambda e: self._set_error('subjects', e)
        )

    def _on_subjects(self, data):
        self._subject_ids = {s['name']: s['id'] for s in data}
        self.subjects = list(self._subject_ids.keys()) if data else ['No subjects found']

    def on_selected_subject(self, instance, value):
        sid = self._subject_ids.get(value)
        if not sid:
            return
        api.set_selection(subject_id=sid)
        self.classes = ['Loading...']
        api.run_in_thread(
            api.get_classes, sid,
            on_success=self._on_classes,
            on_error=lambda e: self._set_error('classes', e)
        )

    def _on_classes(self, data):
        self._class_ids = {c['name']: c['id'] for c in data}
        self.classes = list(self._class_ids.keys()) if data else ['No classes found']

    def on_selected_class(self, instance, value):
        cid = self._class_ids.get(value)
        if cid:
            api.set_selection(class_id=cid)

    def select_class(self):
        sel = api.get_selection()
        if not all([sel['semester_id'], sel['subject_id'], sel['class_id']]):
            print('Please select semester, subject, and class before continuing.')
            return
        App.get_running_app().navigate('documents')

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')
```

**No KV changes needed** — the Spinners already call `on_text: root.selected_semester = self.text` etc., which triggers the `on_selected_*` observers above.

---

## Step 4 — Replace `wizprinter/screens/documents.py` and `kv/documents.kv`

**What currently exists:** Five hardcoded fake dicts in `ListProperty`. The KV also has three hardcoded `DocumentItem` widgets.

**The documents screen = Exams for the selected subject.**  
API: `GET /api/exams/by-subject/{subject_id}`  
Response fields used: `id`, `name`, `created_at`, `status` ("pending" / "graded"), `paper_count`.

### Replace `wizprinter/screens/documents.py`:

```python
"""Document (Exam) list screen."""
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.properties import StringProperty
import wizprinter.api_client as api


class DocumentsScreen(Screen):
    status_text = StringProperty('')

    # Map display name -> exam dict (keeps id for navigation)
    _exam_map = {}

    def on_enter(self):
        sel = api.get_selection()
        subject_id = sel.get('subject_id')
        if not subject_id:
            self.status_text = 'No subject selected.'
            return
        self.status_text = 'Loading exams...'
        self._clear_list()
        api.run_in_thread(
            api.get_exams, subject_id,
            on_success=self._on_exams,
            on_error=self._on_error
        )

    def _clear_list(self):
        if 'doc_list' in self.ids:
            self.ids.doc_list.clear_widgets()

    def _on_exams(self, data):
        self.status_text = ''
        self._exam_map = {}
        container = self.ids.doc_list
        container.clear_widgets()

        if not data:
            from kivy.uix.label import Label
            container.add_widget(Label(
                text='No exams found for this subject.',
                color=(1, 1, 1, 0.5),
                size_hint_y=None,
                height='40dp'
            ))
            return

        from kivy.uix.button import Button
        from kivy.metrics import dp
        for exam in data:
            self._exam_map[exam['name']] = exam
            date_str = exam.get('created_at', '')[:10]
            badge = f"  [{exam.get('status','').upper()}]" if exam.get('status') else ''
            btn = Button(
                text=f"{exam['name']}{badge}\n{date_str}",
                size_hint_y=None,
                height=dp(50),
                halign='left',
                text_size=(None, None),
                font_size='13sp',
            )
            name = exam['name']
            btn.bind(on_release=lambda b, n=name: self.select_document(n))
            container.add_widget(btn)

    def _on_error(self, exc):
        self.status_text = f'Error: {exc}'

    def select_document(self, exam_name):
        exam = self._exam_map.get(exam_name)
        if not exam:
            return
        api.set_selection(exam_id=exam['id'])
        preview_screen = self.manager.get_screen('preview')
        preview_screen.load_document(exam_name)
        self.manager.current = 'preview'

    def go_back(self):
        App.get_running_app().navigate('classes', direction='right')
```

### Replace `kv/documents.kv`:

Remove all hardcoded `DocumentItem` widgets. Keep the structure but make `doc_list` empty so Python populates it:

```kv
#:import dp kivy.metrics.dp

<DocumentsScreen>:
    canvas.before:
        Color:
            rgba: BG_DARK
        Rectangle:
            pos: self.pos
            size: self.size

    BoxLayout:
        orientation: 'vertical'

        StatusBar:
            size_hint_y: None
            height: dp(45)
            title: 'Select Exam'
            show_back: True
            on_back: root.go_back()

        Label:
            text: root.status_text
            size_hint_y: None
            height: dp(24)
            font_size: '12sp'
            color: 1, 0.8, 0.2, 1

        ScrollView:
            size_hint_y: 1
            do_scroll_x: False
            BoxLayout:
                id: doc_list
                orientation: 'vertical'
                size_hint_y: None
                height: self.minimum_height

        BottomNav:
            active_tab: 'documents'
            size_hint_y: None
            height: dp(45)
```

---

## Step 5 — Replace `wizprinter/screens/scan.py` (`upload` method only)

**What currently exists:** `upload()` saves a local PDF under `temp/scan_pdf/latest_scan.pdf` and navigates to preview. No API call from scan itself.

**What to change:** Keep all scanning logic unchanged. Only replace `upload()` so that after building the PDF it:
1. Saves to `temp/scan_pdf/latest_scan.pdf` (under `temp/`, which is gitignored)
2. Stores the pdf path on the preview screen for later grading submission

The actual API call (grading submission) happens from the **Preview screen** when the user taps GRADE, not here. Scan's job is just to produce the PDF and hand off to preview.

Replace only the end of `upload()` after PDF is saved:

```python
    def upload(self):
        """Compiles JPG batch into PDF and switches to Preview."""
        if not self.scanned_images:
            self.status_msg = "NO PAGES"
            return

        self.status_msg = "COMPILING..."
        output_name = 'latest_scan.pdf'
        scan_pdf_dir = os.path.abspath(os.path.join('temp', 'scan_pdf'))
        os.makedirs(scan_pdf_dir, exist_ok=True)
        pdf_path = os.path.join(scan_pdf_dir, output_name)

        try:
            from PIL import Image as PILImage
            images = [PILImage.open(f).convert('RGB') for f in self.scanned_images]
            if images:
                images[0].save(pdf_path, save_all=True, append_images=images[1:])
                self.scanned_images = []

                app = App.get_running_app()
                preview_screen = app.root.get_screen('preview')

                # Tell preview where the PDF is and that it came from scan
                preview_screen.scanned_pdf_path = pdf_path
                preview_screen.load_document('latest_scan.pdf')
                app.navigate('preview')

        except Exception as e:
            self.status_msg = "PDF ERROR"
            print(f"PDF Error: {e}")
```

---

## Step 6 — Replace `wizprinter/screens/preview.py`

**What currently exists:**
- `load_document()` renders JPGs from `temp/` — keep this.
- `grade_document()` calls the real exam grading API (submit, poll, download, print).
- `go_back()` always goes to dashboard.
- No API calls.

**What to replace it with:**

```python
import os
import subprocess
import time
import threading
from kivy.uix.screenmanager import Screen
from kivy.app import App
from kivy.uix.image import Image as KivyImage
from kivy.properties import BooleanProperty, StringProperty
from kivy.clock import Clock
import wizprinter.api_client as api


class PreviewScreen(Screen):
    page_info    = StringProperty('DOC: 0 PGS')
    show_success = BooleanProperty(False)
    success_message = StringProperty('')

    # Set by scan.py before navigating here
    scanned_pdf_path = ''

    def load_document(self, doc_name):
        Clock.schedule_once(self._build_preview, 0.1)

    def _build_preview(self, dt):
        container = self.ids.preview_container
        container.clear_widgets()
        temp_dir = 'temp'
        if os.path.exists(temp_dir):
            files = sorted([
                os.path.join(temp_dir, f)
                for f in os.listdir(temp_dir)
                if f.endswith('.jpg')
            ])
            self.page_info = f"DOC: {len(files)} PGS"
            for path in files:
                img = KivyImage(
                    source=path,
                    size_hint_y=None,
                    height=container.width * 1.41,
                    allow_stretch=True,
                    keep_ratio=True
                )
                img.reload()
                container.add_widget(img)

    def go_back(self):
        App.get_running_app().navigate('dashboard', direction='right')

    def delete_document(self):
        # Wipe temp scans
        temp_dir = 'temp'
        if os.path.exists(temp_dir):
            for f in os.listdir(temp_dir):
                if f.endswith('.jpg'):
                    os.remove(os.path.join(temp_dir, f))
        self.scanned_pdf_path = ''
        App.get_running_app().navigate('dashboard', direction='right')

    def grade_document(self):
        """Submit scanned PDF to backend for grading, poll, download, print."""
        sel = api.get_selection()
        exam_id  = sel.get('exam_id')
        class_id = sel.get('class_id')
        pdf_path = self.scanned_pdf_path

        if not exam_id:
            self.success_message = 'No exam selected. Go back and select an exam.'
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, 'show_success', False), 3.0)
            return

        if not class_id:
            self.success_message = 'No class selected. Go back and select a class.'
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, 'show_success', False), 3.0)
            return

        if not pdf_path or not os.path.exists(pdf_path):
            self.success_message = 'No scanned PDF found.'
            self.show_success = True
            Clock.schedule_once(lambda dt: setattr(self, 'show_success', False), 3.0)
            return

        self.success_message = 'Submitting for grading...'
        self.show_success = True

        api.run_in_thread(
            api.submit_grading_session, exam_id, class_id, pdf_path,
            on_success=self._on_submitted,
            on_error=self._on_grade_error
        )

    def _on_submitted(self, data):
        # Determine whether we got a batch_id or session_id
        batch_id   = data.get('batch_id')
        session_id = data.get('session_id')

        self.success_message = 'Grading in progress...'

        if batch_id:
            self._poll_batch(batch_id)
        elif session_id:
            self._poll_session(session_id)
        else:
            self._on_grade_error(Exception(f"Unexpected response: {data}"))

    def _poll_batch(self, batch_id, attempt=0):
        """Poll GET /api/batches/{batch_id} every 10s until done."""
        def do_poll():
            try:
                status = api.get_batch_status(batch_id)
                Clock.schedule_once(lambda dt: self._handle_batch_status(status, batch_id), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_grade_error(e), 0)
        threading.Thread(target=do_poll, daemon=True).start()

    def _handle_batch_status(self, status, batch_id):
        total     = status.get('total', 1)
        completed = status.get('completed', 0)
        failed    = status.get('failed', 0)
        overall   = status.get('status', '')

        self.success_message = f"Grading... {completed}/{total} done"

        if overall == 'completed' or (completed + failed) >= total:
            # Find the first completed session's graded_url
            sessions = status.get('sessions', [])
            graded_url = None
            for s in sessions:
                if s.get('status') == 'completed' and s.get('graded_url'):
                    graded_url = s['graded_url']
                    break
            if graded_url:
                self._download_and_print(graded_url)
            else:
                self.success_message = 'Grading complete (no PDF returned).'
                Clock.schedule_once(self._finish, 3.0)
        else:
            # Keep polling every 10 seconds
            Clock.schedule_once(lambda dt: self._poll_batch(batch_id), 10.0)

    def _poll_session(self, session_id, attempt=0):
        """Poll GET /api/sessions/{session_id} every 10s until done."""
        def do_poll():
            try:
                status = api.get_session_status(session_id)
                Clock.schedule_once(lambda dt: self._handle_session_status(status, session_id), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_grade_error(e), 0)
        threading.Thread(target=do_poll, daemon=True).start()

    def _handle_session_status(self, status, session_id):
        state = status.get('status', '')
        self.success_message = f"Grading... ({state})"

        if state == 'completed':
            graded_url = status.get('graded_url')
            if graded_url:
                self._download_and_print(graded_url)
            else:
                self.success_message = 'Grading complete (no PDF returned).'
                Clock.schedule_once(self._finish, 3.0)
        elif state == 'failed':
            self._on_grade_error(Exception(status.get('error', 'Grading failed')))
        else:
            Clock.schedule_once(lambda dt: self._poll_session(session_id), 10.0)

    def _download_and_print(self, graded_url):
        self.success_message = 'Downloading graded PDF...'
        dest = os.path.abspath(os.path.join('temp', 'graded_result.pdf'))

        def do_download():
            try:
                api.download_graded_pdf(graded_url, dest)
                Clock.schedule_once(lambda dt: self._send_to_printer(dest), 0)
            except Exception as e:
                Clock.schedule_once(lambda dt: self._on_grade_error(e), 0)

        threading.Thread(target=do_download, daemon=True).start()

    def _send_to_printer(self, pdf_path):
        self.success_message = 'Printing...'
        try:
            if os.path.exists(pdf_path):
                subprocess.run(['lp', pdf_path], check=True)
                self.success_message = 'Grading complete! Printed.'
            else:
                self.success_message = 'Graded PDF not found.'
        except Exception as e:
            self.success_message = f'Print error: {e}'
        Clock.schedule_once(self._finish, 3.0)

    def _on_grade_error(self, exc):
        self.success_message = f'Error: {exc}'
        self.show_success = True
        Clock.schedule_once(self._finish, 4.0)

    def _finish(self, dt):
        self.show_success = False
        App.get_running_app().navigate('dashboard')

    def print_document(self):
        """Print the locally scanned PDF without grading."""
        pdf_path = self.scanned_pdf_path
        if not pdf_path or not os.path.exists(pdf_path):
            return
        try:
            subprocess.run(['lp', pdf_path], check=True)
        except Exception as e:
            print(f'Print error: {e}')
```

---

## Step 7 — Update `wizprinter/screens/settings.py` (logout)

Replace `logout()` to clear the session token:

```python
def logout(self):
    import wizprinter.api_client as api
    api.clear_session()
    App.get_running_app().navigate('landing', direction='right')
```

---

## Step 8 — Add Back button to `kv/scan.kv`

Currently `go_back()` exists in Python but there is no button for it in the KV. Add a Back button to the right-side controls column, above the `+ PAGE` button:

```kv
# BACK
Button:
    text: 'BACK'
    font_size: '11sp'
    size_hint_y: 0.8
    background_color: (0, 0, 0, 0)
    on_release: root.go_back()
    canvas.before:
        Color:
            rgba: (0.2, 0.1, 0.1, 1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [6]
```

---

## Full API Reference (backend source-verified)

| Method | Path | Auth | Notes |
|--------|------|------|-------|
| POST | Firebase REST sign-in | none | Returns `idToken` |
| POST | `/api/professors/onboard` | Bearer | Returns `{ id, email, name, credits }` |
| GET  | `/api/semesters` | Bearer | List professor's semesters |
| GET  | `/api/subjects?semester_id=<uuid>` | Bearer | List subjects for semester |
| GET  | `/api/classes/by-subject/<uuid>` | Bearer | List classes for subject |
| GET  | `/api/exams/by-subject/<uuid>` | Bearer | List exams (documents) for subject |
| POST | `/api/exams/<uuid>/grade` | Bearer | Multipart: `class_id` + `file` (field name is `file`) |
| GET  | `/api/batches/<uuid>` | Bearer | Poll batch — stop when `(completed+failed)==total` |
| GET  | `/api/sessions/<uuid>` | Bearer | Poll single session — stop when `status==completed/failed` |
| GET  | graded_url (SAS URL) | none | Direct download, no auth header needed |

---

## What NOT to use

- **`POST /api/grade-paper`** — do not call this from the Pi. It is the web UI's "quick grade" feature that requires a full master key JSON. The Pi uses the exam-based flow above.
- **`GET /api/jobs/{jobId}/status`** — this is the polling endpoint for `/api/grade-paper` jobs only. Not needed on the Pi.

---

## Session State Flow

```
Login screen
  → firebase_sign_in(email, pwd)          → stores _token
  → onboard_professor()                   → stores _professor_id
  → navigate to dashboard

Classes screen (on_enter)
  → get_semesters()                       → user picks one → stores _selected_semester_id
  → get_subjects(semester_id)             → user picks one → stores _selected_subject_id
  → get_classes(subject_id)              → user picks one → stores _selected_class_id
  → navigate to documents

Documents screen (on_enter)
  → get_exams(subject_id)                → user picks one → stores _selected_exam_id
  → navigate to preview

Scan screen
  → hardware scan → build PDF → store path on preview_screen.scanned_pdf_path
  → navigate to preview

Preview screen — GRADE button
  → submit_grading_session(exam_id, class_id, pdf_path)
  → poll get_batch_status / get_session_status every 10s
  → when completed: download_graded_pdf(graded_url, dest)
  → lp dest
  → navigate to dashboard

Settings — Logout
  → clear_session()                       → clears all state
  → navigate to landing
```
