"""Shared pytest fixtures for the DMXX backend test-suite."""
import asyncio
import os
import sys
import types

import pytest

# Make the repository root importable so `import backend...` works.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ---------------------------------------------------------------------------
# asyncio.create_task shim
#
# Large parts of DMXInterface are synchronous but fire-and-forget coroutines
# via asyncio.create_task() (websocket broadcasts, output sends).  In a plain
# sync test there is no running loop, so those calls raise RuntimeError.  This
# autouse fixture swaps create_task for a recorder that closes the coroutine.
# ---------------------------------------------------------------------------
class TaskRecorder:
    """Collects coroutines handed to asyncio.create_task and closes them."""

    def __init__(self):
        self.calls = []

    def __call__(self, coro, *args, **kwargs):
        name = getattr(coro, "__qualname__", None) or getattr(
            getattr(coro, "cr_code", None), "co_name", "?"
        )
        self.calls.append(name)
        close = getattr(coro, "close", None)
        if close:
            close()
        return _DummyTask()

    @property
    def count(self):
        return len(self.calls)

    def names(self):
        return list(self.calls)


class _DummyTask:
    def cancel(self):
        return True

    def done(self):
        return True


@pytest.fixture
def task_recorder(monkeypatch):
    """Replace asyncio.create_task with a recorder (no event loop needed)."""
    recorder = TaskRecorder()
    monkeypatch.setattr(asyncio, "create_task", recorder)
    return recorder


@pytest.fixture(autouse=True)
def _no_stray_tasks(request, monkeypatch):
    """Autouse safety net so sync tests never hit 'no running event loop'.

    Tests that want to assert on scheduled coroutines should request the
    explicit `task_recorder` fixture instead; this one just keeps the rest
    of the suite from exploding.
    """
    if "task_recorder" in request.fixturenames:
        return
    if "asyncio" in request.keywords:  # real loop present, leave it alone
        return
    monkeypatch.setattr(asyncio, "create_task", TaskRecorder())


# ---------------------------------------------------------------------------
# DMX interface fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def dmx():
    """A fresh, empty DMXInterface (no universes, no outputs)."""
    from backend.dmx_interface import DMXInterface

    return DMXInterface()


@pytest.fixture
def dmx1(dmx):
    """DMXInterface with universe 1 present but no outputs configured."""
    from backend.dmx_interface import DMXUniverse

    dmx.universes[1] = DMXUniverse(1)
    return dmx


@pytest.fixture
def dmx12(dmx):
    """DMXInterface with universes 1 and 2 present."""
    from backend.dmx_interface import DMXUniverse

    dmx.universes[1] = DMXUniverse(1)
    dmx.universes[2] = DMXUniverse(2)
    return dmx


@pytest.fixture
def events(dmx):
    """Register a recording callback on the `dmx` fixture.

    Returns a list of (event_type, data) tuples appended in real time.
    """
    captured = []

    def _cb(event_type, data):
        captured.append((event_type, data))

    dmx.register_callback(_cb)
    return captured


# ---------------------------------------------------------------------------
# Database fixtures - an isolated on-disk SQLite per test
# ---------------------------------------------------------------------------
@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture
def db_engine(db_path):
    """An engine bound to a throw-away SQLite file with the schema created."""
    from sqlalchemy import create_engine
    from backend.database import Base

    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_sessionmaker(db_engine):
    """A sessionmaker for code that opens its own sessions (SessionLocal)."""
    from sqlalchemy.orm import sessionmaker

    return sessionmaker(autocommit=False, autoflush=False, bind=db_engine)


@pytest.fixture
def db_session(db_sessionmaker):
    """A SQLAlchemy session bound to a throw-away SQLite file."""
    session = db_sessionmaker()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers shared across API tests
# ---------------------------------------------------------------------------
@pytest.fixture
def make_app(db_session):
    """Build a minimal FastAPI app around a router with deps overridden.

    Usage::

        client = make_app(scenes_router, prefix="/api/scenes")
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.database import get_db
    from backend import auth as auth_module

    def _build(router, prefix="", user=None):
        app = FastAPI()
        app.include_router(router, prefix=prefix)

        def _get_db_override():
            yield db_session

        default_user = {
            "authenticated": True,
            "method": "token",
            "ip": "127.0.0.1",
            "profile_id": 1,
            "profile_name": "Admin",
            "allowed_pages": ["faders", "scenes", "fixtures", "patch", "io",
                              "groups", "midi", "settings", "monitor", "help"],
            "allowed_grids": None,
            "allowed_scenes": None,
            "is_admin": True,
            "can_park": True,
            "can_highlight": True,
            "can_bypass": True,
        }
        if user is not None:
            default_user.update(user)

        async def _user_override():
            return default_user

        app.dependency_overrides[get_db] = _get_db_override
        app.dependency_overrides[auth_module.get_current_user] = _user_override
        app.dependency_overrides[auth_module.optional_auth] = _user_override
        return TestClient(app)

    return _build


def make_artnet_packet(universe=0, values=None, sequence=1, length=None):
    """Build a valid ArtDmx packet for input/monitor parser tests."""
    import struct

    values = list(values or [])
    if length is None:
        length = len(values)
    header = b"Art-Net\x00"
    header += struct.pack("<H", 0x5000)      # OpDmx
    header += struct.pack(">H", 14)          # protocol version
    header += bytes([sequence, 0])           # sequence, physical
    header += struct.pack("<H", universe)    # universe (lo/hi)
    header += struct.pack(">H", length)      # data length
    return header + bytes(values)


def make_sacn_packet(universe=1, values=None, start_code=0):
    """Build a minimally-valid E1.31 packet for parser tests."""
    import struct

    values = list(values or [])
    packet = bytearray(126)
    packet[4:16] = b"\x41\x53\x43\x2d\x45\x31\x2e\x31\x37\x00\x00\x00"  # ACN id
    packet[113:115] = struct.pack(">H", universe)
    packet[125] = start_code
    return bytes(packet) + bytes(values)
