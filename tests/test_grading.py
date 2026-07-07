"""Unit tests for wizprinter.grading — confidence flags, review state, grouping."""
from wizprinter.grading import (
    GROUP_FAILED, GROUP_HIGH_CONFIDENCE, GROUP_NEEDS_REVIEW,
    GradeOutputMode, ReviewState, all_approved, flagged_response_count,
    group_for_session, group_sessions, initial_review_state,
    response_needs_review, session_key, session_needs_review,
)


def _resp(confidence=None, override=None):
    return {"question": "Q", "answer": "A", "confidence": confidence, "override": override}


class TestResponseNeedsReview:
    def test_low_confidence_flagged(self):
        assert response_needs_review(_resp(confidence=0.5)) is True

    def test_at_threshold_flagged(self):
        assert response_needs_review(_resp(confidence=0.75)) is True

    def test_high_confidence_not_flagged(self):
        assert response_needs_review(_resp(confidence=0.99)) is False

    def test_missing_confidence_not_flagged(self):
        assert response_needs_review(_resp(confidence=None)) is False

    def test_override_clears_flag_even_if_low_confidence(self):
        assert response_needs_review(_resp(confidence=0.1, override="corrected")) is False

    def test_non_numeric_confidence_not_flagged(self):
        assert response_needs_review(_resp(confidence="n/a")) is False


class TestSessionLevel:
    def test_flagged_response_count(self):
        session = {"responses": [_resp(0.9), _resp(0.4), _resp(0.2)]}
        assert flagged_response_count(session) == 2

    def test_session_needs_review_true(self):
        session = {"responses": [_resp(0.9), _resp(0.1)]}
        assert session_needs_review(session) is True

    def test_session_needs_review_false_when_no_responses(self):
        assert session_needs_review({}) is False

    def test_initial_review_state_flagged(self):
        session = {"responses": [_resp(0.1)]}
        assert initial_review_state(session) == ReviewState.FLAGGED

    def test_initial_review_state_pending(self):
        session = {"responses": [_resp(0.99)]}
        assert initial_review_state(session) == ReviewState.PENDING

    def test_session_key_prefers_session_id(self):
        assert session_key({"session_id": "s1", "id": "i1"}) == "s1"

    def test_session_key_falls_back_to_id(self):
        assert session_key({"id": "i1"}) == "i1"

    def test_session_key_missing(self):
        assert session_key({}) == ""


class TestGrouping:
    def test_group_for_session_failed_takes_priority(self):
        session = {"status": "failed", "responses": [_resp(0.99)]}
        assert group_for_session(session) == GROUP_FAILED

    def test_group_for_session_needs_review(self):
        session = {"status": "completed", "responses": [_resp(0.1)]}
        assert group_for_session(session) == GROUP_NEEDS_REVIEW

    def test_group_for_session_high_confidence(self):
        session = {"status": "completed", "responses": [_resp(0.99)]}
        assert group_for_session(session) == GROUP_HIGH_CONFIDENCE

    def test_group_sessions_buckets_all(self):
        sessions = [
            {"session_id": "a", "status": "failed"},
            {"session_id": "b", "status": "completed", "responses": [_resp(0.1)]},
            {"session_id": "c", "status": "completed", "responses": [_resp(0.9)]},
        ]
        groups = group_sessions(sessions)
        assert [s["session_id"] for s in groups[GROUP_FAILED]] == ["a"]
        assert [s["session_id"] for s in groups[GROUP_NEEDS_REVIEW]] == ["b"]
        assert [s["session_id"] for s in groups[GROUP_HIGH_CONFIDENCE]] == ["c"]

    def test_group_sessions_empty_input(self):
        groups = group_sessions([])
        assert all(v == [] for v in groups.values())


class TestApprovalGuard:
    def test_all_approved_true(self):
        sessions = [{"session_id": "a"}, {"session_id": "b"}]
        approvals = {"a": ReviewState.APPROVED, "b": ReviewState.APPROVED}
        assert all_approved(sessions, approvals) is True

    def test_all_approved_false_when_one_missing(self):
        sessions = [{"session_id": "a"}, {"session_id": "b"}]
        approvals = {"a": ReviewState.APPROVED, "b": ReviewState.FLAGGED}
        assert all_approved(sessions, approvals) is False

    def test_all_approved_false_when_empty(self):
        assert all_approved([], {}) is False


class TestOutputMode:
    def test_two_modes_exist(self):
        assert GradeOutputMode.PRINT_AND_SEND != GradeOutputMode.SEND_ONLY
