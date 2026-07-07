"""
Grading domain logic: output modes, confidence flagging, review state,
and client-side grouping.

These are pure functions/dataclasses with no Kivy dependency, so they can be
unit tested directly and are shared by PreviewScreen, GradingStatusMixin, and
ReviewScreen.

Data-shape note (missing backend contract)
-------------------------------------------
The grading backend does not yet document a stable per-student / per-response
shape or an analytics-grouping endpoint. Everything below is written
defensively against dicts with optional keys, and the grouping in this module
is a *client-side heuristic* standing in for real backend analytics. The
assumed shape, once a session is graded, is:

    session = {
        "session_id": str,
        "student_name": str,          # optional, falls back to session_id
        "status": "completed" | "failed" | ...,
        "graded_url": str,
        "responses": [                 # optional — may be absent entirely
            {
                "question":   str,
                "answer":     str,
                "confidence": float,    # 0.0..1.0, optional
                "correct":    bool | None,
                "override":   str | None,   # teacher's corrected answer/grade
            },
            ...
        ],
    }

If/when the backend documents a real shape (or an analytics-grouping
endpoint), swap `group_sessions()`'s body for a direct API call and keep the
same return type so ReviewScreen doesn't need to change.
"""
from __future__ import annotations

import enum


# ── Output mode ───────────────────────────────────────────────────────────────

class GradeOutputMode(enum.Enum):
    """The two actions offered by the Grade Output popup."""
    PRINT_AND_SEND = "print_and_send"   # grade, print locally, AND sync to WizPrinter
    SEND_ONLY      = "send_only"        # grade and sync to WizPrinter, skip local print


# ── Confidence ────────────────────────────────────────────────────────────────

LOW_CONFIDENCE_THRESHOLD = 0.75  # responses at/below this need teacher review


def response_needs_review(response: dict) -> bool:
    """True if a single graded response should be flagged for teacher review."""
    if response.get("override") is not None:
        return False  # teacher already corrected this one
    confidence = response.get("confidence")
    if confidence is None:
        return False  # no confidence signal from the grader -> nothing to flag
    try:
        return float(confidence) <= LOW_CONFIDENCE_THRESHOLD
    except (TypeError, ValueError):
        return False


def flagged_response_count(session: dict) -> int:
    return sum(1 for r in session.get("responses", []) if response_needs_review(r))


def session_needs_review(session: dict) -> bool:
    """True if any response in this student's session is flagged for review."""
    return flagged_response_count(session) > 0


# ── Per-student review state ─────────────────────────────────────────────────

class ReviewState(enum.Enum):
    PENDING  = "pending"    # no low-confidence responses; not yet explicitly approved
    FLAGGED  = "flagged"    # has low-confidence responses awaiting teacher attention
    APPROVED = "approved"   # teacher has reviewed/corrected and approved this student


def initial_review_state(session: dict) -> ReviewState:
    return ReviewState.FLAGGED if session_needs_review(session) else ReviewState.PENDING


def session_key(session: dict) -> str:
    """Stable identifier for a session dict, tolerant of either key name."""
    return session.get("session_id") or session.get("id") or ""


def all_approved(sessions: list[dict], approvals: dict[str, ReviewState]) -> bool:
    """True only once every session has an explicit APPROVED state."""
    for s in sessions:
        if approvals.get(session_key(s)) != ReviewState.APPROVED:
            return False
    return bool(sessions)


# ── Client-side grouping heuristic (stand-in for backend analytics) ─────────

GROUP_NEEDS_REVIEW    = "Needs Review"
GROUP_HIGH_CONFIDENCE = "High Confidence"
GROUP_FAILED          = "Failed / Error"

GROUP_ORDER = (GROUP_NEEDS_REVIEW, GROUP_FAILED, GROUP_HIGH_CONFIDENCE)


def group_for_session(session: dict) -> str:
    if session.get("status") == "failed":
        return GROUP_FAILED
    if session_needs_review(session):
        return GROUP_NEEDS_REVIEW
    return GROUP_HIGH_CONFIDENCE


def group_sessions(sessions: list[dict]) -> dict[str, list[dict]]:
    """Bucket sessions into named groups for the review screen's grouping panel.

    NOTE: this is a client-side heuristic, not real backend analytics — see
    module docstring. Replace with a direct API call once one exists, keeping
    this same return shape (dict[group_name] -> list[session]).
    """
    groups: dict[str, list[dict]] = {name: [] for name in GROUP_ORDER}
    for s in sessions:
        groups[group_for_session(s)].append(s)
    return groups
