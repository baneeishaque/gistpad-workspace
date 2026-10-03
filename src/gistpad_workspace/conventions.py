"""Naming and protocol conventions shared with gistpad-mcp and VS Code Gistpad."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timezone

ARCHIVED_SUFFIX = " [Archived]"
DUPLICATE_SUFFIX = " (Copy)"
DAILY_GIST_DESCRIPTION = "📆 Daily notes"
PROMPTS_GIST_DESCRIPTION = "💬 Prompts"
EMPTY_FILE_SENTINEL = "\u2064"

MAX_SLUG_LENGTH = 48
FALLBACK_SLUG = "untitled"

_ARCHIVED_RE = re.compile(re.escape(ARCHIVED_SUFFIX) + r"$")
_NON_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(description: str | None) -> str:
    """Kebab-case slug for a gist description: ASCII, lowercase, hyphen-joined."""
    text = unicodedata.normalize("NFKD", description or "")
    ascii_text = text.encode("ascii", "ignore").decode("ascii").lower()
    slug = _NON_SLUG_RE.sub("-", ascii_text).strip("-")
    slug = slug[:MAX_SLUG_LENGTH].strip("-")
    return slug or FALLBACK_SLUG


def gist_dir_name(description: str | None, gist_id: str) -> str:
    """Workspace directory name: ``<kebab-slug>--<first-8-of-id>``."""
    return f"{slugify(description)}--{gist_id[:8]}"


def is_archived(description: str | None) -> bool:
    return bool(description) and bool(_ARCHIVED_RE.search(description))


def archive_description(description: str | None) -> str:
    base = description or ""
    if is_archived(base):
        return base
    return base + ARCHIVED_SUFFIX


def unarchive_description(description: str | None) -> str:
    if not description:
        return ""
    return _ARCHIVED_RE.sub("", description)


def is_daily_gist(description: str | None) -> bool:
    return description == DAILY_GIST_DESCRIPTION


def is_prompts_gist(description: str | None) -> bool:
    return description == PROMPTS_GIST_DESCRIPTION


def duplicate_description(description: str | None) -> str:
    return (description or "") + DUPLICATE_SUFFIX


def encode_file_content(content: str) -> str:
    """GitHub cannot store truly empty gist files; use the shared sentinel."""
    return content if content else EMPTY_FILE_SENTINEL


def today_iso() -> str:
    return date.today().isoformat()


def daily_file_name(date_iso: str) -> str:
    return f"{date_iso}.md"


def render_daily_content(template: str | None, date_iso: str) -> str:
    """Daily-note body from an optional template; ``{{date}}`` becomes ISO."""
    if template:
        return template.replace("{{date}}", date_iso)
    return f"# {date_iso}\n\n"


def gist_url(gist_id: str) -> str:
    return f"https://gist.github.com/{gist_id}"


def parse_github_timestamp(value: str) -> datetime:
    """Parse GitHub ISO-8601 timestamps (with ``Z``) on Python 3.9."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
