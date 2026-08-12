# DMXX backend test-suite

Unit tests for everything under `backend/`: the DMX engine, protocol parsers,
MIDI integration, database models/migrations, auth, and every API router.

## Running

```bash
pip install -r requirements-dev.txt
pytest                       # whole suite
pytest tests/test_auth.py    # one module
pytest --cov=backend         # with coverage
```

## Layout

| File | Covers |
|------|--------|
| `test_config.py` | page registry |
| `test_auth.py` | JWT, IP matching, whitelists, page/admin guards |
| `test_database.py` | models, constraints, `init_db()` and every migration branch |
| `test_dmx_universe.py` | the 512-channel value container |
| `test_dmx_interface_channels.py` | set/get channels, sources, blackout, universes & outputs |
| `test_dmx_interface_masters.py` | grand-master scaling, park, highlight |
| `test_dmx_interface_groups.py` | group modes, HTP merge, colour mixing, group CRUD |
| `test_dmx_interface_passthrough.py` | HTP/LTP merge, channel mapping, input bypass |
| `test_dmx_interface_midi.py` | CC mappings, note triggers, MIDI feedback |
| `test_dmx_inputs.py` / `test_dmx_outputs.py` | Art-Net & sACN packet parsing, source filters, output factory |
| `test_midi_handler.py` / `test_midi_helpers.py` / `test_midi_network.py` | MIDI dispatch, value conversion, rtpMIDI |
| `test_network_monitor.py` | passive traffic monitor |
| `test_websocket_manager.py` | broadcast/connection bookkeeping |
| `test_api_*.py` | one file per API router |
| `test_main.py` | app wiring, WebSocket protocol, blackout, lifespan |

## Conventions

- Every test gets a throw-away SQLite file (`db_session` / `db_sessionmaker`
  fixtures) — the real `data/database.db` is never touched.
- API tests build a minimal FastAPI app around a single router via the
  `make_app` fixture, with `get_db` and `get_current_user` overridden. Pass
  `user={...}` to test permission failures.
- Routers hold a module-level reference to the global `dmx_interface`; tests
  monkeypatch that attribute with a private `DMXInterface` so state never leaks
  between tests.
- Synchronous code that fires `asyncio.create_task(...)` is covered by an
  autouse shim; request the `task_recorder` fixture to assert on scheduled
  broadcasts.
- No test opens a socket, binds a port or talks to MIDI hardware.

## Regression guards

Bugs found while writing this suite and since fixed; these tests keep them
fixed:

- **Over-broad IP whitelist.** `is_ip_whitelisted()` matched wildcards with a
  bare string prefix, so `192.168.1.*` also admitted `192.168.11.x` — and
  whitelisted IPs get full admin. It now delegates to `ip_matches()`. Guarded
  by `test_*_whitelist_wildcards_are_octet_aligned`,
  `test_whitelist_matching_agrees_with_ip_matches` and
  `test_a_neighbouring_subnet_is_not_authenticated`.
- **Dead timeout branch.** `_cleanup_loop` tested `age > 5 and source.is_active`
  where `is_active` means `age < 5`, so `monitor_source_timeout` was never
  broadcast. `SourceInfo` now carries a `timeout_notified` flag, cleared when
  traffic resumes. Guarded by the cleanup-loop tests in
  `test_network_monitor.py`.
- **Dropped member fields.** `PUT /groups/{id}/members/{id}` accepted
  `target_type` / `target_universe_id` but never wrote them, silently leaving a
  `channel` member with null universe and channel. Guarded by
  `test_update_can_convert_a_member_to_*`.
- **Broken per-device MIDI disconnect.** `DMXInterface.stop_midi_input()` took
  no arguments while the router passed a device name, so
  `POST /api/midi/input/disconnect` returned 500 every time. Guarded by
  `test_stop_midi_input_forwards_the_device_name` and
  `test_disconnect_a_named_device`.
- **Leaked shared-node reference.** Art-Net/sACN outputs reference-count one
  pyartnet node per destination. A `start()` that failed *after* taking a
  reference (e.g. pyartnet rejecting a duplicate universe) returned `False`
  without giving it back, so the node's socket was never closed and
  `_shared_nodes` kept a stale entry for later outputs to reuse. Both classes
  now release through `_release_node()`. Guarded by
  `test_a_failed_start_returns_its_reference` and the surrounding
  shared-node-lifecycle tests.
- **Out-of-range channel writes.** `set_channel*()` updated their local-value
  bookkeeping before any bounds check, so channel 513 raised `IndexError` and
  channel 0 wrote onto channel 512. The REST API validated first, but the
  WebSocket API did not, so a malformed message dropped the client's socket.
  All three setters now ignore invalid writes (matching `DMXUniverse`).
  Guarded in `test_dmx_interface_channels.py` and, end to end, by
  `test_out_of_range_*` in `test_main.py`.

- **Position off-by-one.** `max(position) or -1` treated an existing max
  position of `0` as "no rows", so the second row created also landed on
  position `0`. Guarded by `test_the_second_*_gets_the_next_position` in the
  group, grid, fixture, patch and scene suites.
- **Shadowed route.** `GET /api/io/channel-usage` was registered after the
  dynamic `/{universe_id}` route, so the literal path was parsed as a universe
  ID and 422'd. Guarded by
  `test_channel_usage_route_is_not_shadowed_by_the_universe_route` and
  `test_channel_usage_is_declared_before_the_dynamic_route`; if anyone reorders
  the router again, both fail.
