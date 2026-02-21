"""
Single source of truth for available pages in Access Profiles.
When adding a new page, add it here and in frontend/src/config/pages.js
"""

AVAILABLE_PAGES = [
    {"id": "faders", "name": "Faders"},
    {"id": "scenes", "name": "Scenes"},
    {"id": "fixtures", "name": "Fixtures"},
    {"id": "patch", "name": "Patch"},
    {"id": "io", "name": "I/O"},
    {"id": "groups", "name": "Groups"},
    {"id": "midi", "name": "MIDI"},
    {"id": "settings", "name": "Settings"},
    {"id": "monitor", "name": "Network Monitor"},
    {"id": "help", "name": "Help"}
]

ALL_PAGE_IDS = [p["id"] for p in AVAILABLE_PAGES]
