"""API tests for the help documentation and network monitor endpoints."""
import pytest

from backend.api import help as help_api
from backend.api import monitor as monitor_api
from backend.network_monitor import NetworkMonitor


# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------
@pytest.fixture
def help_client(make_app):
    return make_app(help_api.router, prefix="/api")


def test_help_document_shape(help_client):
    body = help_client.get("/api/help").json()

    assert body["title"] == "DMXX Input/Output System Documentation"
    assert isinstance(body["sections"], dict)
    assert body["sections"]


def test_help_sections_have_titles(help_client):
    for name, section in help_client.get("/api/help").json()["sections"].items():
        assert section.get("title"), f"section {name} has no title"


def test_help_documents_the_io_flow(help_client):
    io_flow = help_client.get("/api/help").json()["sections"]["io_flow"]

    assert io_flow["flows"]
    for flow in io_flow["flows"]:
        assert flow["mode"]
        assert flow["diagram"]
        assert flow["description"]


def test_help_is_json_serialisable_and_public(help_client):
    response = help_client.get("/api/help")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------
@pytest.fixture
def network_monitor(monkeypatch):
    monitor = NetworkMonitor()
    monkeypatch.setattr(monitor_api, "network_monitor", monitor)
    return monitor


@pytest.fixture
def monitor_client(make_app, network_monitor):
    return make_app(monitor_api.router, prefix="/api/monitor")


def test_monitor_status_when_idle(monitor_client):
    body = monitor_client.get("/api/monitor").json()

    assert body["running"] is False
    assert body["sources"] == {}
    assert body["stats"]["total_sources"] == 0


def test_monitor_status_lists_detected_sources(monitor_client, network_monitor):
    network_monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)

    body = monitor_client.get("/api/monitor").json()
    assert "artnet:10.0.0.1:0" in body["sources"]
    assert body["stats"]["total_sources"] == 1


def test_monitor_stats_endpoint(monitor_client, network_monitor):
    network_monitor.on_packet_received("sacn", "10.0.0.2", 1, [0] * 512)

    stats = monitor_client.get("/api/monitor/stats").json()
    assert stats["sacn_sources"] == 1
    assert stats["total_packets"] == 1


def test_source_detail_includes_all_512_values(monitor_client, network_monitor):
    values = [3] * 512
    network_monitor.on_packet_received("artnet", "10.0.0.1", 0, values)

    body = monitor_client.get("/api/monitor/source/artnet:10.0.0.1:0").json()
    assert body["values"] == values
    assert body["ip"] == "10.0.0.1"


def test_unknown_source_detail_reports_an_error(monitor_client):
    assert monitor_client.get("/api/monitor/source/nope:1:1").json() == {
        "error": "Source not found"}


def test_stop_endpoint_on_an_idle_monitor(monitor_client, network_monitor):
    assert monitor_client.post("/api/monitor/stop").json() == {
        "status": "stopped", "running": False}


def test_start_endpoint_reports_the_running_state(monitor_client,
                                                  network_monitor, monkeypatch):
    async def _start():
        network_monitor._running = True
        return True

    monkeypatch.setattr(network_monitor, "start", _start)

    assert monitor_client.post("/api/monitor/start").json() == {
        "status": "started", "running": True}


def test_start_endpoint_reports_failure(monitor_client, network_monitor,
                                        monkeypatch):
    async def _start():
        return False

    monkeypatch.setattr(network_monitor, "start", _start)

    assert monitor_client.post("/api/monitor/start").json() == {
        "status": "failed", "running": False}


# ---------------------------------------------------------------------------
# Monitor WebSocket
# ---------------------------------------------------------------------------
@pytest.fixture
def monitor_ws_client(network_monitor):
    """A plain app exposing only the monitor router (no auth on /ws)."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(monitor_api.router, prefix="/api/monitor")
    return TestClient(app)


def test_websocket_sends_the_current_state_on_connect(monitor_ws_client,
                                                      network_monitor):
    network_monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)

    with monitor_ws_client.websocket_connect("/api/monitor/ws") as ws:
        message = ws.receive_json()

    assert message["type"] == "monitor_status"
    assert "artnet:10.0.0.1:0" in message["data"]["sources"]


def test_websocket_subscribe_returns_channel_values(monitor_ws_client,
                                                    network_monitor):
    values = [9] * 512
    network_monitor.on_packet_received("artnet", "10.0.0.1", 0, values)

    with monitor_ws_client.websocket_connect("/api/monitor/ws") as ws:
        ws.receive_json()  # initial status
        ws.send_json({"type": "subscribe_source",
                      "source_key": "artnet:10.0.0.1:0"})
        message = ws.receive_json()

    assert message["type"] == "monitor_source_values"
    assert message["data"]["values"] == values


def test_websocket_unsubscribe(monitor_ws_client, network_monitor):
    first, second = "artnet:10.0.0.1:0", "artnet:10.0.0.2:0"
    network_monitor.on_packet_received("artnet", "10.0.0.1", 0, [0] * 512)
    network_monitor.on_packet_received("artnet", "10.0.0.2", 0, [0] * 512)

    with monitor_ws_client.websocket_connect("/api/monitor/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "subscribe_source", "source_key": first})
        ws.receive_json()

        ws.send_json({"type": "unsubscribe_source", "source_key": first})
        ws.send_json({"type": "subscribe_source"})  # missing key, ignored
        ws.send_json({"type": "unsubscribe_source"})  # missing key, ignored
        ws.send_json({"type": "noop"})  # unknown type, ignored
        # Subscribing to a second source round-trips, so by the time this
        # response arrives every message above has been processed.
        ws.send_json({"type": "subscribe_source", "source_key": second})
        ws.receive_json()

        assert list(network_monitor._subscribed_sources.values()) == [{second}]


def test_websocket_disconnect_deregisters_the_client(monitor_ws_client,
                                                     network_monitor):
    with monitor_ws_client.websocket_connect("/api/monitor/ws") as ws:
        ws.receive_json()
        assert network_monitor.get_stats()["connected_clients"] == 1

    assert network_monitor.get_stats()["connected_clients"] == 0
