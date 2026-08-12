"""Tests for the ORM models, schema creation and the migration routine."""
import json
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from backend import database as db_module
from backend.database import (
    Backup,
    Base,
    ChannelLabel,
    ChannelMapping,
    Fixture,
    Group,
    GroupGrid,
    GroupMember,
    IPWhitelist,
    MIDICCMapping,
    MIDITrigger,
    ParkedChannel,
    Patch,
    Profile,
    Scene,
    SceneGroupValue,
    SceneMasterValue,
    SceneValue,
    Setting,
    TriggerToken,
    Universe,
    UniverseOutput,
    User,
    get_db,
)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
def test_all_tables_are_created(db_session):
    tables = set(inspect(db_session.get_bind()).get_table_names())
    expected = {
        "users", "ip_whitelist", "universes", "fixtures", "patch", "scenes",
        "scene_values", "scene_group_values", "scene_master_values", "backups",
        "settings", "profiles", "channel_labels", "channel_mappings",
        "universe_outputs", "group_grids", "groups", "group_members",
        "trigger_tokens", "midi_cc_mappings", "midi_triggers", "parked_channels",
    }
    assert expected <= tables


def test_get_db_yields_and_closes_a_session():
    generator = get_db()
    session = next(generator)
    assert session is not None
    with pytest.raises(StopIteration):
        next(generator)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
def test_universe_defaults(db_session):
    universe = Universe(label="Main", device_type="artnet")
    db_session.add(universe)
    db_session.commit()

    assert universe.enabled is True
    assert universe.input_type == "none"
    assert universe.input_enabled is False
    assert universe.passthrough_enabled is False
    assert universe.passthrough_mode == "htp"
    assert universe.input_channel_start == 1
    assert universe.input_channel_end == 512
    assert universe.master_fader_color == "#00bcd4"


def test_universe_label_and_device_type_are_required(db_session):
    db_session.add(Universe(label="No device"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_group_defaults(db_session):
    group = Group(name="Warm")
    db_session.add(group)
    db_session.commit()

    assert group.mode == "proportional"
    assert group.master_value == 0
    assert group.enabled is True
    assert (group.color_state_h, group.color_state_s, group.color_state_l) == (0, 0, 100)
    assert group.position == 0
    assert group.master_universe is None


def test_group_member_defaults(db_session):
    group = Group(name="G")
    db_session.add(group)
    db_session.commit()

    member = GroupMember(group_id=group.id, universe_id=1, channel=1)
    db_session.add(member)
    db_session.commit()

    assert member.base_value == 255
    assert member.target_type == "channel"
    assert member.color_role is None


def test_scene_defaults(db_session):
    scene = Scene(name="Blackout")
    db_session.add(scene)
    db_session.commit()

    assert scene.transition_type == "instant"
    assert scene.duration == 0
    assert scene.position == 0


def test_channel_mapping_defaults(db_session):
    mapping = ChannelMapping(name="Desk")
    db_session.add(mapping)
    db_session.commit()

    assert mapping.enabled is False
    assert mapping.unmapped_behavior == "passthrough"
    assert mapping.mappings_json == {"mappings": []}


def test_midi_mapping_defaults(db_session):
    cc = MIDICCMapping(cc_number=7, input_channel=1)
    trigger = MIDITrigger(note=60, action="scene")
    db_session.add_all([cc, trigger])
    db_session.commit()

    assert cc.midi_channel == -1
    assert cc.enabled is True
    assert cc.device_name is None
    assert trigger.midi_channel == -1
    assert trigger.enabled is True


def test_universe_output_defaults(db_session):
    universe = Universe(label="U", device_type="mock")
    db_session.add(universe)
    db_session.commit()

    output = UniverseOutput(universe_id=universe.id, device_type="artnet")
    db_session.add(output)
    db_session.commit()

    assert output.enabled is True
    assert output.priority == 0
    assert output.config_json == {}


def test_profile_permission_defaults(db_session):
    profile = Profile(name="Operator", allowed_pages=["faders"])
    db_session.add(profile)
    db_session.commit()

    assert profile.is_admin is False
    assert profile.can_park is True
    assert profile.can_highlight is True
    assert profile.can_bypass is True
    assert profile.ip_addresses is None


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------
def test_profile_names_are_unique(db_session):
    db_session.add(Profile(name="Admin", allowed_pages=[]))
    db_session.commit()

    db_session.add(Profile(name="Admin", allowed_pages=[]))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_whitelist_entries_are_unique(db_session):
    db_session.add(IPWhitelist(ip_address="10.0.0.1"))
    db_session.commit()

    db_session.add(IPWhitelist(ip_address="10.0.0.1"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_trigger_tokens_are_unique(db_session):
    db_session.add(TriggerToken(token="abc", created_at="now"))
    db_session.commit()

    db_session.add(TriggerToken(token="abc", created_at="now"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_trigger_token_defaults(db_session):
    token = TriggerToken(token="xyz", created_at="2026-01-01")
    db_session.add(token)
    db_session.commit()

    assert token.token_type == "scene"
    assert token.scene_id is None
    assert token.group_id is None
    assert token.last_used is None


def test_user_requires_a_password_hash(db_session):
    db_session.add(User())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_setting_key_is_the_primary_key(db_session):
    db_session.add(Setting(key="theme", value="dark"))
    db_session.commit()
    assert db_session.query(Setting).filter_by(key="theme").one().value == "dark"


# ---------------------------------------------------------------------------
# JSON columns
# ---------------------------------------------------------------------------
def test_json_columns_round_trip(db_session):
    profile = Profile(
        name="Tech",
        allowed_pages=["faders", "scenes"],
        allowed_grids=[1, 2],
        allowed_scenes=[5],
        ip_addresses=["10.0.0.*"],
    )
    db_session.add(profile)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.query(Profile).filter_by(name="Tech").one()
    assert loaded.allowed_pages == ["faders", "scenes"]
    assert loaded.allowed_grids == [1, 2]
    assert loaded.allowed_scenes == [5]
    assert loaded.ip_addresses == ["10.0.0.*"]


def test_fixture_definition_json_round_trip(db_session):
    definition = {"channels": [{"name": "Dimmer", "type": "intensity"}]}
    fixture = Fixture(name="PAR", definition_json=definition)
    db_session.add(fixture)
    db_session.commit()
    db_session.expire_all()

    assert db_session.query(Fixture).one().definition_json == definition


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------
def test_patch_links_fixture_and_universe(db_session):
    fixture = Fixture(name="PAR", definition_json={})
    universe = Universe(label="U1", device_type="mock")
    db_session.add_all([fixture, universe])
    db_session.commit()

    patch = Patch(fixture_id=fixture.id, universe_id=universe.id, start_channel=1)
    db_session.add(patch)
    db_session.commit()

    assert patch.fixture.name == "PAR"
    assert patch.universe.label == "U1"
    assert universe.patches == [patch]
    assert fixture.patches == [patch]


def test_scene_values_cascade_on_delete(db_session):
    scene = Scene(name="Look")
    db_session.add(scene)
    db_session.commit()

    db_session.add_all([
        SceneValue(scene_id=scene.id, universe_id=1, channel=1, value=255),
        SceneGroupValue(scene_id=scene.id, group_id=1, master_value=128),
        SceneMasterValue(scene_id=scene.id, master_type="global", value=200),
    ])
    db_session.commit()
    assert len(scene.values) == 1

    db_session.delete(scene)
    db_session.commit()

    assert db_session.query(SceneValue).count() == 0
    assert db_session.query(SceneGroupValue).count() == 0
    assert db_session.query(SceneMasterValue).count() == 0


def test_group_members_cascade_on_delete(db_session):
    group = Group(name="G")
    db_session.add(group)
    db_session.commit()

    db_session.add(GroupMember(group_id=group.id, universe_id=1, channel=1))
    db_session.commit()

    db_session.delete(group)
    db_session.commit()
    assert db_session.query(GroupMember).count() == 0


def test_universe_outputs_cascade_on_delete(db_session):
    universe = Universe(label="U", device_type="mock")
    db_session.add(universe)
    db_session.commit()

    db_session.add(UniverseOutput(universe_id=universe.id, device_type="artnet"))
    db_session.commit()

    db_session.delete(universe)
    db_session.commit()
    assert db_session.query(UniverseOutput).count() == 0


def test_grid_groups_relationship(db_session):
    grid = GroupGrid(name="Stage")
    db_session.add(grid)
    db_session.commit()

    db_session.add(Group(name="G1", grid_id=grid.id))
    db_session.commit()
    db_session.expire_all()

    assert [g.name for g in db_session.query(GroupGrid).one().groups] == ["G1"]


def test_scene_group_value_stores_colour_state(db_session):
    scene = Scene(name="Colour")
    db_session.add(scene)
    db_session.commit()

    value = SceneGroupValue(scene_id=scene.id, group_id=1, master_value=255,
                            color_state_h=180.0, color_state_s=100.0,
                            color_state_l=50.0)
    db_session.add(value)
    db_session.commit()

    assert value.color_state_h == 180.0


def test_simple_models_persist(db_session):
    db_session.add_all([
        Backup(timestamp="2026-01-01T00:00:00", folder_path="/tmp/b"),
        ChannelLabel(universe_id=1, channel=5, label="Front wash"),
        ParkedChannel(universe_id=1, channel=3, value=128),
    ])
    db_session.commit()

    assert db_session.query(Backup).one().comment == ""
    assert db_session.query(ChannelLabel).one().label == "Front wash"
    assert db_session.query(ParkedChannel).one().value == 128


# ---------------------------------------------------------------------------
# init_db / migrations against a throw-away database file
# ---------------------------------------------------------------------------
@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Point the database module at a temporary file."""
    path = str(tmp_path / "data" / "database.db")
    engine = create_engine(f"sqlite:///{path}",
                           connect_args={"check_same_thread": False})
    os.makedirs(os.path.dirname(path), exist_ok=True)

    monkeypatch.setattr(db_module, "DATABASE_PATH", path)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal",
                        sessionmaker(autocommit=False, autoflush=False, bind=engine))
    yield path
    engine.dispose()


def test_init_db_creates_the_file_and_tables(temp_db):
    db_module.init_db()

    assert os.path.exists(temp_db)
    with sqlite3.connect(temp_db) as conn:
        tables = {row[0] for row in
                  conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"universes", "profiles", "groups", "group_grids"} <= tables


def test_init_db_seeds_an_admin_profile(temp_db):
    db_module.init_db()

    session = db_module.SessionLocal()
    try:
        admin = session.query(Profile).filter_by(name="Admin").one()
        assert admin.is_admin is True
        assert set(admin.allowed_pages) == set(db_module.ALL_PAGE_IDS)
    finally:
        session.close()


def test_init_db_uses_the_password_from_config(temp_db):
    db_module.init_db()

    config_path = os.path.join(os.path.dirname(db_module.__file__), "..", "config.json")
    expected = "dmxx"
    if os.path.exists(config_path):
        with open(config_path) as handle:
            expected = json.load(handle).get("password", "dmxx")

    session = db_module.SessionLocal()
    try:
        assert session.query(Profile).filter_by(name="Admin").one().password == expected
    finally:
        session.close()


def test_init_db_is_idempotent(temp_db):
    db_module.init_db()
    db_module.init_db()

    session = db_module.SessionLocal()
    try:
        assert session.query(Profile).count() == 1
    finally:
        session.close()


def test_init_db_creates_a_default_grid(temp_db):
    db_module.init_db()

    session = db_module.SessionLocal()
    try:
        assert session.query(GroupGrid).one().name == "Groups"
    finally:
        session.close()


def test_migration_adds_missing_columns_to_a_legacy_schema(temp_db):
    """A pre-migration profiles table gains the newer permission columns."""
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            password TEXT,
            allowed_pages TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(profiles)")}
    conn.close()
    assert {"ip_addresses", "allowed_grids", "allowed_scenes",
            "can_park", "can_highlight", "can_bypass"} <= columns


def test_migration_moves_legacy_universe_outputs(temp_db):
    """A universe carrying legacy output columns is copied into universe_outputs."""
    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    conn.execute(
        "INSERT INTO universes (label, device_type, config_json, enabled) "
        "VALUES ('Legacy', 'artnet', '{\"ip\": \"10.0.0.1\"}', 1)"
    )
    conn.commit()
    conn.close()

    db_module.init_db()  # re-run migrations

    conn = sqlite3.connect(temp_db)
    rows = conn.execute(
        "SELECT device_type, config_json FROM universe_outputs").fetchall()
    conn.close()
    assert rows == [("artnet", '{"ip": "10.0.0.1"}')]


def test_migration_backfills_position_columns(temp_db):
    """Rows created before `position` existed get sequential positions."""
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            transition_type TEXT DEFAULT 'instant',
            duration INTEGER DEFAULT 0
        )
    """)
    conn.executemany("INSERT INTO scenes (name) VALUES (?)",
                     [("a",), ("b",), ("c",)])
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT name, position FROM scenes ORDER BY id").fetchall()
    conn.close()
    assert rows == [("a", 0), ("b", 1), ("c", 2)]


def test_migration_makes_group_master_columns_nullable(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mode TEXT DEFAULT 'proportional',
            master_universe INTEGER NOT NULL,
            master_channel INTEGER NOT NULL,
            master_value INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT 1
        )
    """)
    conn.execute("INSERT INTO groups (name, master_universe, master_channel) "
                 "VALUES ('legacy', 1, 5)")
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    notnull = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(groups)")}
    surviving = conn.execute("SELECT name FROM groups").fetchall()
    conn.close()

    assert notnull["master_universe"] == 0
    assert notnull["master_channel"] == 0
    assert surviving == [("legacy",)]


def test_migration_drops_universe_id_from_cc_mappings(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE midi_cc_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe_id INTEGER NOT NULL,
            cc_number INTEGER NOT NULL,
            input_channel INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(midi_cc_mappings)")}
    conn.close()
    assert "universe_id" not in columns
    assert "device_name" in columns


def test_migration_makes_trigger_token_scene_id_nullable(temp_db):
    conn = sqlite3.connect(temp_db)
    conn.execute("""
        CREATE TABLE trigger_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            scene_id INTEGER NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL,
            last_used TEXT
        )
    """)
    conn.execute("INSERT INTO trigger_tokens (token, scene_id, created_at) "
                 "VALUES ('t1', 3, 'now')")
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    info = {row[1]: row[3] for row in conn.execute("PRAGMA table_info(trigger_tokens)")}
    rows = conn.execute("SELECT token, token_type, scene_id FROM trigger_tokens").fetchall()
    conn.close()

    assert info["scene_id"] == 0  # now nullable
    assert rows == [("t1", "scene", 3)]


def test_migration_assigns_existing_groups_to_the_default_grid(temp_db):
    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    conn.execute("DELETE FROM group_grids")
    conn.execute("INSERT INTO groups (name, grid_id) VALUES ('Orphan', NULL)")
    conn.commit()
    conn.close()

    db_module.init_db()

    conn = sqlite3.connect(temp_db)
    grid_id = conn.execute("SELECT id FROM group_grids").fetchone()[0]
    group_grid = conn.execute("SELECT grid_id FROM groups WHERE name='Orphan'").fetchone()[0]
    conn.close()
    assert group_grid == grid_id
