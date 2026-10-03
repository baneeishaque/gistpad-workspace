"""Tests for gistpad-workspace conventions."""

from __future__ import annotations

import pytest

from gistpad_workspace.conventions import (
    ARCHIVED_SUFFIX,
    DAILY_GIST_DESCRIPTION,
    EMPTY_FILE_SENTINEL,
    PROMPTS_GIST_DESCRIPTION,
    archive_description,
    daily_file_name,
    duplicate_description,
    encode_file_content,
    gist_dir_name,
    gist_url,
    is_archived,
    is_daily_gist,
    is_prompts_gist,
    parse_github_timestamp,
    render_daily_content,
    slugify,
    unarchive_description,
)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("My Notes", "my-notes"),
        ("  Spaces  &  Symbols!! ", "spaces-symbols"),
        ("📆 Daily notes", "daily-notes"),
        ("💬 Prompts", "prompts"),
        ("Café Notes", "cafe-notes"),
        ("", "untitled"),
        (None, "untitled"),
        ("---", "untitled"),
        ("a" * 80, "a" * 48),
        ("a" * 47 + " b", "a" * 47),
    ],
)
def test_slugify(description: str | None, expected: str) -> None:
    assert slugify(description) == expected


def test_gist_dir_name() -> None:
    assert gist_dir_name("My Notes", "0123456789abcdef") == "my-notes--01234567"


def test_archive_round_trip() -> None:
    assert archive_description("Notes") == "Notes" + ARCHIVED_SUFFIX
    assert archive_description("Notes" + ARCHIVED_SUFFIX) == "Notes" + ARCHIVED_SUFFIX
    assert is_archived("Notes" + ARCHIVED_SUFFIX)
    assert not is_archived("Notes")
    assert not is_archived(None)
    assert unarchive_description("Notes" + ARCHIVED_SUFFIX) == "Notes"
    assert unarchive_description("Notes") == "Notes"


def test_archive_is_case_sensitive() -> None:
    assert not is_archived("Notes [archived]")


def test_daily_and_prompts_detection() -> None:
    assert is_daily_gist(DAILY_GIST_DESCRIPTION)
    assert not is_daily_gist("Daily notes")
    assert is_prompts_gist(PROMPTS_GIST_DESCRIPTION)
    assert not is_prompts_gist("Prompts")


def test_duplicate_description() -> None:
    assert duplicate_description("Notes") == "Notes (Copy)"
    assert duplicate_description(None) == " (Copy)"


def test_empty_file_sentinel() -> None:
    assert encode_file_content("") == EMPTY_FILE_SENTINEL
    assert encode_file_content("x") == "x"


def test_daily_helpers() -> None:
    assert daily_file_name("2026-10-03") == "2026-10-03.md"
    assert render_daily_content(None, "2026-10-03") == "# 2026-10-03\n\n"
    assert render_daily_content("# 📆 {{date}}\n", "2026-10-03") == "# 📆 2026-10-03\n"


def test_gist_url() -> None:
    assert gist_url("abc123") == "https://gist.github.com/abc123"


def test_parse_github_timestamp_handles_z_suffix() -> None:
    parsed = parse_github_timestamp("2026-10-03T11:00:00Z")
    assert parsed.isoformat() == "2026-10-03T11:00:00+00:00"
    assert parsed.tzinfo is not None
