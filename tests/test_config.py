"""Tests for backend.config - the page registry."""
import pytest

from backend.config import AVAILABLE_PAGES, ALL_PAGE_IDS


def test_all_pages_have_id_and_name():
    for page in AVAILABLE_PAGES:
        assert set(page.keys()) == {"id", "name"}
        assert page["id"]
        assert page["name"]


def test_page_ids_are_unique():
    assert len(ALL_PAGE_IDS) == len(set(ALL_PAGE_IDS))


def test_all_page_ids_matches_available_pages():
    assert ALL_PAGE_IDS == [p["id"] for p in AVAILABLE_PAGES]


def test_core_pages_present():
    for expected in ("faders", "scenes", "fixtures", "patch", "io",
                     "groups", "midi", "settings", "monitor", "help"):
        assert expected in ALL_PAGE_IDS


def test_page_ids_are_lowercase_slugs():
    for page_id in ALL_PAGE_IDS:
        assert page_id == page_id.lower()
        assert " " not in page_id


# ---------------------------------------------------------------------------
# Cross-language parity
#
# backend/config.py and frontend/src/config/pages.js each declare themselves
# the "single source of truth" for Access Profile pages and tell the reader to
# update the other. Nothing enforced that, so the two could drift silently -
# a page added on one side only would be grantable but unreachable, or shown
# but never authorised.
# ---------------------------------------------------------------------------
import os
import re

FRONTEND_PAGES_JS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend", "src", "config", "pages.js",
)


def parse_frontend_pages():
    """Extract the PAGES array from the frontend module."""
    with open(FRONTEND_PAGES_JS) as handle:
        source = handle.read()

    body = re.search(r"export const PAGES = \[(.*?)\n\]", source, re.S)
    assert body, "could not locate the PAGES array in pages.js"

    pages = []
    for entry in re.finditer(r"\{\s*id:\s*'([^']+)'\s*,\s*name:\s*'([^']+)'\s*\}",
                             body.group(1)):
        pages.append({"id": entry.group(1), "name": entry.group(2)})
    return pages


@pytest.mark.skipif(not os.path.exists(FRONTEND_PAGES_JS),
                    reason="frontend sources not present")
def test_frontend_and_backend_page_registries_match():
    assert parse_frontend_pages() == AVAILABLE_PAGES


@pytest.mark.skipif(not os.path.exists(FRONTEND_PAGES_JS),
                    reason="frontend sources not present")
def test_the_parser_actually_found_pages():
    """Guard against the parity test passing because the regex matched nothing."""
    parsed = parse_frontend_pages()
    assert len(parsed) == len(AVAILABLE_PAGES) > 0
