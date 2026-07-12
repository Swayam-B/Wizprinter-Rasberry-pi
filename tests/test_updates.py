"""Unit tests for wizprinter.updates version comparison (kivy-free path)."""
from wizprinter.updates import _parse_version, is_newer


class TestParseVersion:
    def test_plain(self):
        assert _parse_version("2.6.0") == (2, 6, 0)

    def test_v_prefix_and_whitespace(self):
        assert _parse_version("  v2.6.0 ") == (2, 6, 0)

    def test_non_numeric_chunks_default_to_zero(self):
        assert _parse_version("2.6.0-rc1") == (2, 6, 0)

    def test_empty(self):
        assert _parse_version("") == (0,)


class TestIsNewer:
    def test_strictly_newer(self):
        assert is_newer("2.6.0", current="2.5.0") is True

    def test_same_is_not_newer(self):
        assert is_newer("2.5.0", current="2.5.0") is False

    def test_older_is_not_newer(self):
        assert is_newer("2.4.9", current="2.5.0") is False

    def test_patch_bump(self):
        assert is_newer("2.5.1", current="2.5.0") is True

    def test_shorter_version_strings_compare(self):
        assert is_newer("3", current="2.9.9") is True
