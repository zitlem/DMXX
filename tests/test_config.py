"""Tests for backend.config - the page registry."""
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
