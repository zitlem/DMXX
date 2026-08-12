"""Tests for the WebSocket connection manager."""
import pytest

from backend.websocket_manager import ConnectionManager, manager


class FakeWebSocket:
    def __init__(self, fail=False):
        self.accepted = False
        self.sent = []
        self.fail = fail

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        if self.fail:
            raise ConnectionError("client gone")
        self.sent.append(message)


@pytest.fixture
def cm():
    return ConnectionManager()


# ---------------------------------------------------------------------------
# Connect / disconnect
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_connect_accepts_and_registers(cm):
    ws = FakeWebSocket()
    client_id = await cm.connect(ws)

    assert ws.accepted is True
    assert ws in cm.active_connections
    assert cm.client_ids[ws] == client_id
    assert len(client_id) == 8


@pytest.mark.asyncio
async def test_client_ids_are_unique(cm):
    ids = {await cm.connect(FakeWebSocket()) for _ in range(5)}
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_disconnect_removes_the_client(cm):
    ws = FakeWebSocket()
    await cm.connect(ws)

    cm.disconnect(ws)
    assert ws not in cm.active_connections
    assert ws not in cm.client_ids


def test_disconnecting_an_unknown_client_is_safe(cm):
    cm.disconnect(FakeWebSocket())
    assert cm.active_connections == set()


# ---------------------------------------------------------------------------
# Broadcast
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broadcast_reaches_every_client(cm):
    clients = [FakeWebSocket() for _ in range(3)]
    for ws in clients:
        await cm.connect(ws)

    await cm.broadcast({"type": "hello"})
    assert all(ws.sent == [{"type": "hello"}] for ws in clients)


@pytest.mark.asyncio
async def test_broadcast_with_no_clients_is_a_noop(cm):
    await cm.broadcast({"type": "hello"})


@pytest.mark.asyncio
async def test_broadcast_prunes_dead_connections(cm):
    good, bad = FakeWebSocket(), FakeWebSocket(fail=True)
    await cm.connect(good)
    await cm.connect(bad)

    await cm.broadcast({"type": "hello"})

    assert bad not in cm.active_connections
    assert good in cm.active_connections


@pytest.mark.asyncio
async def test_send_personal_targets_one_client(cm):
    a, b = FakeWebSocket(), FakeWebSocket()
    await cm.connect(a)
    await cm.connect(b)

    await cm.send_personal(a, {"type": "just-for-you"})

    assert a.sent == [{"type": "just-for-you"}]
    assert b.sent == []


@pytest.mark.asyncio
async def test_send_personal_drops_a_dead_client(cm):
    bad = FakeWebSocket(fail=True)
    await cm.connect(bad)

    await cm.send_personal(bad, {"type": "x"})
    assert bad not in cm.active_connections


# ---------------------------------------------------------------------------
# Typed broadcast helpers
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("method,expected", [
    ("broadcast_scenes_changed", {"type": "scenes_changed"}),
    ("broadcast_patches_changed", {"type": "patches_changed"}),
    ("broadcast_groups_changed", {"type": "groups_changed"}),
    ("broadcast_grids_changed", {"type": "grids_changed"}),
])
async def test_simple_change_notifications(cm, method, expected):
    ws = FakeWebSocket()
    await cm.connect(ws)

    await getattr(cm, method)()
    assert ws.sent == [expected]


@pytest.mark.asyncio
async def test_group_value_changed_payload(cm):
    ws = FakeWebSocket()
    await cm.connect(ws)

    await cm.broadcast_group_value_changed(3, 128)
    assert ws.sent[-1] == {
        "type": "group_value_changed",
        "data": {"group_id": 3, "value": 128},
    }


@pytest.mark.asyncio
async def test_group_value_changed_includes_source_when_given(cm):
    ws = FakeWebSocket()
    await cm.connect(ws)

    await cm.broadcast_group_value_changed(3, 128, source="input")
    assert ws.sent[-1]["data"]["source"] == "input"


def test_module_exposes_a_singleton_manager():
    assert isinstance(manager, ConnectionManager)
