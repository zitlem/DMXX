from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, ForeignKey, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

from .config import ALL_PAGE_IDS

DATABASE_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'database.db')
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    password_hash = Column(String, nullable=False)


class IPWhitelist(Base):
    __tablename__ = "ip_whitelist"
    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, nullable=False)


class Universe(Base):
    __tablename__ = "universes"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    # Legacy output settings (kept for backwards compatibility, migrated to UniverseOutput)
    device_type = Column(String, nullable=False)  # artnet, sacn, mock, etc.
    config_json = Column(JSON, default={})
    enabled = Column(Boolean, default=True)
    # Input settings
    input_type = Column(String, default="none")  # none, artnet_input, sacn_input
    input_config = Column(JSON, default={})
    input_enabled = Column(Boolean, default=False)
    # Passthrough settings (input -> output)
    passthrough_enabled = Column(Boolean, default=False)
    passthrough_mode = Column(String, default="htp")  # htp (highest takes precedence), ltp (latest takes precedence)
    passthrough_show_ui = Column(Boolean, default=False)  # Show input values on faders
    # Input channel range (for scene recall - channels in this range are skipped when input is active)
    input_channel_start = Column(Integer, default=1)
    input_channel_end = Column(Integer, default=512)
    # Master fader color
    master_fader_color = Column(String, default="#00bcd4")  # Teal default for universe master
    patches = relationship("Patch", back_populates="universe")
    outputs = relationship("UniverseOutput", back_populates="universe", cascade="all, delete-orphan")


class Fixture(Base):
    __tablename__ = "fixtures"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    manufacturer = Column(String, default="")
    definition_json = Column(JSON, nullable=False)
    position = Column(Integer, default=0)  # Display order for drag-and-drop rearrangement
    patches = relationship("Patch", back_populates="fixture")


class Patch(Base):
    __tablename__ = "patch"
    id = Column(Integer, primary_key=True, index=True)
    fixture_id = Column(Integer, ForeignKey("fixtures.id"), nullable=False)
    universe_id = Column(Integer, ForeignKey("universes.id"), nullable=False)
    start_channel = Column(Integer, nullable=False)
    label = Column(String, default="")
    group_color = Column(String, default="")  # Hex color for fader stripe grouping
    position = Column(Integer, default=0)  # Display order for drag-and-drop rearrangement
    fixture = relationship("Fixture", back_populates="patches")
    universe = relationship("Universe", back_populates="patches")


class Scene(Base):
    __tablename__ = "scenes"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    transition_type = Column(String, default="instant")  # instant, fade, crossfade
    duration = Column(Integer, default=0)  # milliseconds
    position = Column(Integer, default=0)  # Display order for drag-and-drop rearrangement
    values = relationship("SceneValue", back_populates="scene", cascade="all, delete-orphan")
    group_values = relationship("SceneGroupValue", back_populates="scene", cascade="all, delete-orphan")
    master_values = relationship("SceneMasterValue", back_populates="scene", cascade="all, delete-orphan")


class SceneValue(Base):
    __tablename__ = "scene_values"
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    universe_id = Column(Integer, nullable=False)
    channel = Column(Integer, nullable=False)
    value = Column(Integer, nullable=False)
    scene = relationship("Scene", back_populates="values")


class SceneGroupValue(Base):
    """Group master value stored as part of a scene."""
    __tablename__ = "scene_group_values"
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    group_id = Column(Integer, nullable=False)  # Not FK - group might be deleted later
    master_value = Column(Integer, nullable=False)
    # Color state for color_mixer groups
    color_state_h = Column(Float, nullable=True)  # Hue 0-360
    color_state_s = Column(Float, nullable=True)  # Saturation 0-100
    color_state_l = Column(Float, nullable=True)  # Lightness 0-100
    scene = relationship("Scene", back_populates="group_values")


class SceneMasterValue(Base):
    """Grandmaster values stored as part of a scene."""
    __tablename__ = "scene_master_values"
    id = Column(Integer, primary_key=True, index=True)
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=False)
    master_type = Column(String, nullable=False)  # "global" or "universe"
    universe_id = Column(Integer, nullable=True)  # Only for master_type="universe"
    value = Column(Integer, nullable=False)
    scene = relationship("Scene", back_populates="master_values")


class Backup(Base):
    __tablename__ = "backups"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String, nullable=False)
    comment = Column(String, default="")
    folder_path = Column(String, nullable=False)


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=True)  # Optional if using IP-based auth
    ip_addresses = Column(JSON, nullable=True)  # ["192.168.1.100", "10.0.0.*"]
    allowed_pages = Column(JSON, nullable=False)  # ["faders", "scenes", ...]
    allowed_grids = Column(JSON, nullable=True)  # [1, 2, ...] - null/empty = all grids
    allowed_scenes = Column(JSON, nullable=True)  # [1, 2, ...] - null/empty = all scenes
    is_admin = Column(Boolean, default=False)
    can_park = Column(Boolean, default=True)      # Can park/unpark channels
    can_highlight = Column(Boolean, default=True) # Can use highlight/solo mode
    can_bypass = Column(Boolean, default=True)    # Can toggle input bypass


class ChannelLabel(Base):
    __tablename__ = "channel_labels"
    id = Column(Integer, primary_key=True, index=True)
    universe_id = Column(Integer, nullable=False)
    channel = Column(Integer, nullable=False)
    label = Column(String, nullable=False)


class ChannelMapping(Base):
    """Custom input-to-output channel mapping configuration."""
    __tablename__ = "channel_mappings"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    enabled = Column(Boolean, default=False)
    unmapped_behavior = Column(String, default="passthrough")  # "passthrough" or "ignore"
    mappings_json = Column(JSON, default={"mappings": []})
    # mappings format: [{"src_universe": 1, "src_channel": 1, "dst_universe": 2, "dst_channel": 7}, ...]


class UniverseOutput(Base):
    """Multiple outputs per universe - allows sending to multiple destinations."""
    __tablename__ = "universe_outputs"
    id = Column(Integer, primary_key=True, index=True)
    universe_id = Column(Integer, ForeignKey("universes.id"), nullable=False)
    device_type = Column(String, nullable=False)  # artnet, sacn, mock
    config_json = Column(JSON, default={})
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=0)  # for ordering
    universe = relationship("Universe", back_populates="outputs")


class GroupGrid(Base):
    """Grid container for organizing groups into visual sections."""
    __tablename__ = "group_grids"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    position = Column(Integer, default=0)  # Display order for grids
    color = Column(String, nullable=True)  # Custom color for vertical title bar (hex)
    groups = relationship("Group", back_populates="grid")


class Group(Base):
    """Group/Master for controlling multiple channels with one fader."""
    __tablename__ = "groups"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    mode = Column(String, default="proportional")  # "proportional" or "follow"
    master_universe = Column(Integer, nullable=True)  # Optional - for DMX-linked masters
    master_channel = Column(Integer, nullable=True)   # Optional - for DMX-linked masters
    master_value = Column(Integer, default=0)         # Current virtual master value (0-255)
    enabled = Column(Boolean, default=True)
    color = Column(String, nullable=True)             # Custom fader color (hex)
    color_state_h = Column(Float, default=0)          # Color mixer HSL - Hue (0-360)
    color_state_s = Column(Float, default=0)          # Color mixer HSL - Saturation (0-100)
    color_state_l = Column(Float, default=100)        # Color mixer HSL - Lightness (0-100)
    position = Column(Integer, default=0)             # Display order for drag-and-drop rearrangement
    grid_id = Column(Integer, ForeignKey("group_grids.id"), nullable=True)  # Which grid this group belongs to
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    grid = relationship("GroupGrid", back_populates="groups")


class GroupMember(Base):
    """Member channel of a group."""
    __tablename__ = "group_members"
    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)
    # For channel targets (target_type="channel")
    universe_id = Column(Integer, nullable=True)  # Nullable for virtual targets
    channel = Column(Integer, nullable=True)       # Nullable for virtual targets
    base_value = Column(Integer, default=255)  # For proportional mode scaling
    # Virtual target support (universe_master, global_master)
    target_type = Column(String, default="channel")  # "channel", "universe_master", "global_master"
    target_universe_id = Column(Integer, nullable=True)  # For universe_master target
    # Color mixer support
    color_role = Column(String, nullable=True)  # red, green, blue, white, amber, uv, lime, cyan, magenta, yellow, orange
    group = relationship("Group", back_populates="members")


class TriggerToken(Base):
    """API tokens for remote actions (scenes, blackout, groups, status)."""
    __tablename__ = "trigger_tokens"
    id = Column(Integer, primary_key=True, index=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    token_type = Column(String, nullable=False, default="scene")  # scene, blackout, group, status
    scene_id = Column(Integer, ForeignKey("scenes.id"), nullable=True)  # For scene tokens
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True)  # For group tokens
    name = Column(String, nullable=True)  # Label like "Home Assistant"
    created_at = Column(String, nullable=False)
    last_used = Column(String, nullable=True)
    scene = relationship("Scene", backref="trigger_tokens")
    group = relationship("Group", backref="trigger_tokens")


class MIDICCMapping(Base):
    """Maps MIDI CC to input channels (applies to all universes with MIDI input)."""
    __tablename__ = "midi_cc_mappings"
    id = Column(Integer, primary_key=True, index=True)
    cc_number = Column(Integer, nullable=False)  # 0-127
    midi_channel = Column(Integer, default=-1)   # -1 = any channel
    input_channel = Column(Integer, nullable=False)  # 1-512
    label = Column(String, default="")  # Optional label for UI
    enabled = Column(Boolean, default=True)
    device_name = Column(String, nullable=True)  # None = all devices


class MIDITrigger(Base):
    """Maps MIDI notes to direct actions (scene recall, blackout, group control)."""
    __tablename__ = "midi_triggers"
    id = Column(Integer, primary_key=True, index=True)
    note = Column(Integer, nullable=False)       # 0-127 (MIDI note number)
    midi_channel = Column(Integer, default=-1)   # -1 = any channel
    action = Column(String, nullable=False)      # "scene", "blackout", "group"
    target_id = Column(Integer, nullable=True)   # scene_id, group_id (null for blackout)
    label = Column(String, default="")  # Optional label for UI
    enabled = Column(Boolean, default=True)
    device_name = Column(String, nullable=True)  # None = all devices


class ParkedChannel(Base):
    """Stores parked channels that are locked to a fixed value."""
    __tablename__ = "parked_channels"
    id = Column(Integer, primary_key=True, index=True)
    universe_id = Column(Integer, ForeignKey("universes.id"), nullable=False)
    channel = Column(Integer, nullable=False)  # 1-512
    value = Column(Integer, nullable=False)    # 0-255


def init_db():
    """Initialize the database and create tables."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)

    # Run migrations for new columns
    _run_migrations()


def _run_migrations():
    """Add any missing columns to existing tables and seed default data."""
    import sqlite3
    import json
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Check if group_color column exists in patch table
    cursor.execute("PRAGMA table_info(patch)")
    columns = [col[1] for col in cursor.fetchall()]

    if 'group_color' not in columns:
        cursor.execute("ALTER TABLE patch ADD COLUMN group_color TEXT DEFAULT ''")
        conn.commit()

    # Check if ip_addresses column exists in profiles table
    cursor.execute("PRAGMA table_info(profiles)")
    profile_columns = [col[1] for col in cursor.fetchall()]

    if 'ip_addresses' not in profile_columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN ip_addresses TEXT DEFAULT NULL")
        conn.commit()

    if 'allowed_grids' not in profile_columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN allowed_grids TEXT DEFAULT NULL")
        conn.commit()

    if 'allowed_scenes' not in profile_columns:
        cursor.execute("ALTER TABLE profiles ADD COLUMN allowed_scenes TEXT DEFAULT NULL")
        conn.commit()

    # Add permission columns to profiles table
    for col in ['can_park', 'can_highlight', 'can_bypass']:
        if col not in profile_columns:
            cursor.execute(f"ALTER TABLE profiles ADD COLUMN {col} BOOLEAN DEFAULT 1")
            conn.commit()

    # Create default admin profile if no profiles exist
    cursor.execute("SELECT COUNT(*) FROM profiles")
    profile_count = cursor.fetchone()[0]

    if profile_count == 0:
        # Load password from config.json
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.json')
        default_password = "dmxx"
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    default_password = config.get("password", "dmxx")
            except:
                pass

        # Create admin profile with all pages allowed
        all_pages = json.dumps(ALL_PAGE_IDS)
        cursor.execute(
            "INSERT INTO profiles (name, password, allowed_pages, is_admin) VALUES (?, ?, ?, ?)",
            ("Admin", default_password, all_pages, True)
        )
        conn.commit()

    # Create channel_mappings table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS channel_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 0,
            unmapped_behavior TEXT DEFAULT 'passthrough',
            mappings_json TEXT DEFAULT '{\"mappings\": []}'
        )
    """)
    conn.commit()

    # Create universe_outputs table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS universe_outputs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe_id INTEGER NOT NULL,
            device_type TEXT NOT NULL,
            config_json TEXT DEFAULT '{}',
            enabled BOOLEAN DEFAULT 1,
            priority INTEGER DEFAULT 0,
            FOREIGN KEY (universe_id) REFERENCES universes(id)
        )
    """)
    conn.commit()

    # Migrate existing universe output settings to universe_outputs table
    # Check if any universes exist that don't have corresponding universe_outputs
    cursor.execute("SELECT id, device_type, config_json, enabled FROM universes")
    universes = cursor.fetchall()
    for universe_id, device_type, config_json_str, enabled in universes:
        # Check if this universe already has outputs in the new table
        cursor.execute("SELECT COUNT(*) FROM universe_outputs WHERE universe_id = ?", (universe_id,))
        output_count = cursor.fetchone()[0]
        if output_count == 0 and device_type:
            # Migrate the legacy output to the new table
            cursor.execute(
                "INSERT INTO universe_outputs (universe_id, device_type, config_json, enabled, priority) VALUES (?, ?, ?, ?, ?)",
                (universe_id, device_type, config_json_str or '{}', enabled, 0)
            )
    conn.commit()

    # Create groups table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            mode TEXT DEFAULT 'proportional',
            master_universe INTEGER,
            master_channel INTEGER,
            master_value INTEGER DEFAULT 0,
            enabled BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()

    # Add master_value column to groups table if it doesn't exist
    cursor.execute("PRAGMA table_info(groups)")
    group_columns = [col[1] for col in cursor.fetchall()]
    if 'master_value' not in group_columns:
        cursor.execute("ALTER TABLE groups ADD COLUMN master_value INTEGER DEFAULT 0")
        conn.commit()

    # Add color column to groups table if it doesn't exist
    cursor.execute("PRAGMA table_info(groups)")
    group_columns = [col[1] for col in cursor.fetchall()]
    if 'color' not in group_columns:
        cursor.execute("ALTER TABLE groups ADD COLUMN color TEXT DEFAULT NULL")
        conn.commit()

    # Add position column to groups table if it doesn't exist
    cursor.execute("PRAGMA table_info(groups)")
    group_columns = [col[1] for col in cursor.fetchall()]
    if 'position' not in group_columns:
        cursor.execute("ALTER TABLE groups ADD COLUMN position INTEGER DEFAULT 0")
        conn.commit()
        # Initialize positions based on current ID order
        cursor.execute("SELECT id FROM groups ORDER BY id")
        groups_list = cursor.fetchall()
        for idx, (group_id,) in enumerate(groups_list):
            cursor.execute("UPDATE groups SET position = ? WHERE id = ?", (idx, group_id))
        conn.commit()

    # Add position column to scenes table if it doesn't exist
    cursor.execute("PRAGMA table_info(scenes)")
    scene_columns = [col[1] for col in cursor.fetchall()]
    if 'position' not in scene_columns:
        cursor.execute("ALTER TABLE scenes ADD COLUMN position INTEGER DEFAULT 0")
        conn.commit()
        # Initialize positions based on current ID order
        cursor.execute("SELECT id FROM scenes ORDER BY id")
        scenes_list = cursor.fetchall()
        for idx, (scene_id,) in enumerate(scenes_list):
            cursor.execute("UPDATE scenes SET position = ? WHERE id = ?", (idx, scene_id))
        conn.commit()

    # Add position column to fixtures table if it doesn't exist
    cursor.execute("PRAGMA table_info(fixtures)")
    fixture_columns = [col[1] for col in cursor.fetchall()]
    if 'position' not in fixture_columns:
        cursor.execute("ALTER TABLE fixtures ADD COLUMN position INTEGER DEFAULT 0")
        conn.commit()
        # Initialize positions based on current ID order
        cursor.execute("SELECT id FROM fixtures ORDER BY id")
        fixtures_list = cursor.fetchall()
        for idx, (fixture_id,) in enumerate(fixtures_list):
            cursor.execute("UPDATE fixtures SET position = ? WHERE id = ?", (idx, fixture_id))
        conn.commit()

    # Add position column to patch table if it doesn't exist
    cursor.execute("PRAGMA table_info(patch)")
    patch_columns = [col[1] for col in cursor.fetchall()]
    if 'position' not in patch_columns:
        cursor.execute("ALTER TABLE patch ADD COLUMN position INTEGER DEFAULT 0")
        conn.commit()
        # Initialize positions based on current ID order
        cursor.execute("SELECT id FROM patch ORDER BY id")
        patches_list = cursor.fetchall()
        for idx, (patch_id,) in enumerate(patches_list):
            cursor.execute("UPDATE patch SET position = ? WHERE id = ?", (idx, patch_id))
        conn.commit()

    # Migration: Make master_universe and master_channel nullable
    # Check if they have NOT NULL constraints by looking at column info
    cursor.execute("PRAGMA table_info(groups)")
    columns_info = cursor.fetchall()
    needs_migration = False
    for col in columns_info:
        # col format: (cid, name, type, notnull, dflt_value, pk)
        if col[1] in ('master_universe', 'master_channel') and col[3] == 1:  # notnull=1
            needs_migration = True
            break

    if needs_migration:
        # SQLite doesn't support ALTER COLUMN, so we need to recreate the table
        cursor.execute("ALTER TABLE groups RENAME TO groups_old")
        cursor.execute("""
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mode TEXT DEFAULT 'proportional',
                master_universe INTEGER,
                master_channel INTEGER,
                master_value INTEGER DEFAULT 0,
                enabled BOOLEAN DEFAULT 1
            )
        """)
        cursor.execute("""
            INSERT INTO groups (id, name, mode, master_universe, master_channel, master_value, enabled)
            SELECT id, name, mode, master_universe, master_channel, master_value, enabled
            FROM groups_old
        """)
        cursor.execute("DROP TABLE groups_old")
        conn.commit()

    # Create group_members table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            universe_id INTEGER NOT NULL,
            channel INTEGER NOT NULL,
            base_value INTEGER DEFAULT 255,
            FOREIGN KEY (group_id) REFERENCES groups(id)
        )
    """)
    conn.commit()

    # Create scene_group_values table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scene_group_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            master_value INTEGER NOT NULL,
            FOREIGN KEY (scene_id) REFERENCES scenes(id)
        )
    """)
    conn.commit()

    # Create trigger_tokens table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trigger_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            scene_id INTEGER NOT NULL,
            name TEXT,
            created_at TEXT NOT NULL,
            last_used TEXT,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trigger_tokens_token ON trigger_tokens(token)")
    conn.commit()

    # Add token_type column if it doesn't exist (migration for existing databases)
    cursor.execute("PRAGMA table_info(trigger_tokens)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'token_type' not in columns:
        cursor.execute("ALTER TABLE trigger_tokens ADD COLUMN token_type TEXT NOT NULL DEFAULT 'scene'")
        conn.commit()
    if 'group_id' not in columns:
        cursor.execute("ALTER TABLE trigger_tokens ADD COLUMN group_id INTEGER")
        conn.commit()

    # Check if scene_id is NOT NULL (old schema) and migrate to nullable
    cursor.execute("PRAGMA table_info(trigger_tokens)")
    columns_info = cursor.fetchall()
    scene_id_col = next((col for col in columns_info if col[1] == 'scene_id'), None)
    if scene_id_col and scene_id_col[3] == 1:  # notnull = 1 means NOT NULL
        # SQLite doesn't support ALTER COLUMN, so recreate the table
        cursor.execute("ALTER TABLE trigger_tokens RENAME TO trigger_tokens_old")
        cursor.execute("""
            CREATE TABLE trigger_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                token_type TEXT NOT NULL DEFAULT 'scene',
                scene_id INTEGER,
                group_id INTEGER,
                name TEXT,
                created_at TEXT NOT NULL,
                last_used TEXT,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
                FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            INSERT INTO trigger_tokens (id, token, token_type, scene_id, group_id, name, created_at, last_used)
            SELECT id, token, COALESCE(token_type, 'scene'), scene_id, group_id, name, created_at, last_used
            FROM trigger_tokens_old
        """)
        cursor.execute("DROP TABLE trigger_tokens_old")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_trigger_tokens_token ON trigger_tokens(token)")
        conn.commit()

    # Add input_channel_start and input_channel_end columns to universes table
    cursor.execute("PRAGMA table_info(universes)")
    universe_columns = [col[1] for col in cursor.fetchall()]
    if 'input_channel_start' not in universe_columns:
        cursor.execute("ALTER TABLE universes ADD COLUMN input_channel_start INTEGER DEFAULT 1")
        conn.commit()
    if 'input_channel_end' not in universe_columns:
        cursor.execute("ALTER TABLE universes ADD COLUMN input_channel_end INTEGER DEFAULT 512")
        conn.commit()

    # Add master_fader_color column to universes table if it doesn't exist
    cursor.execute("PRAGMA table_info(universes)")
    universe_columns = [col[1] for col in cursor.fetchall()]
    if 'master_fader_color' not in universe_columns:
        cursor.execute("ALTER TABLE universes ADD COLUMN master_fader_color TEXT DEFAULT '#00bcd4'")
        conn.commit()

    # Create group_grids table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_grids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            position INTEGER DEFAULT 0,
            color TEXT
        )
    """)
    conn.commit()

    # Add grid_id column to groups table if it doesn't exist
    cursor.execute("PRAGMA table_info(groups)")
    group_columns = [col[1] for col in cursor.fetchall()]
    if 'grid_id' not in group_columns:
        cursor.execute("ALTER TABLE groups ADD COLUMN grid_id INTEGER REFERENCES group_grids(id)")
        conn.commit()

    # Create default grid and assign existing groups if no grids exist
    cursor.execute("SELECT COUNT(*) FROM group_grids")
    grid_count = cursor.fetchone()[0]
    if grid_count == 0:
        # Create default grid
        cursor.execute("INSERT INTO group_grids (name, position) VALUES (?, ?)", ("Groups", 0))
        default_grid_id = cursor.lastrowid
        # Assign all existing groups to the default grid
        cursor.execute("UPDATE groups SET grid_id = ? WHERE grid_id IS NULL", (default_grid_id,))
        conn.commit()

    # Add target_type and target_universe_id columns to group_members table
    cursor.execute("PRAGMA table_info(group_members)")
    member_columns = [col[1] for col in cursor.fetchall()]
    if 'target_type' not in member_columns:
        cursor.execute("ALTER TABLE group_members ADD COLUMN target_type TEXT DEFAULT 'channel'")
        conn.commit()
    if 'target_universe_id' not in member_columns:
        cursor.execute("ALTER TABLE group_members ADD COLUMN target_universe_id INTEGER")
        conn.commit()

    # Migration: Make universe_id and channel nullable in group_members table
    # This is needed for virtual targets (universe_master, global_master)
    cursor.execute("PRAGMA table_info(group_members)")
    member_col_info = cursor.fetchall()
    needs_member_migration = False
    for col in member_col_info:
        if col[1] in ('universe_id', 'channel') and col[3] == 1:  # notnull=1
            needs_member_migration = True
            break

    if needs_member_migration:
        cursor.execute("ALTER TABLE group_members RENAME TO group_members_old")
        cursor.execute("""
            CREATE TABLE group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                universe_id INTEGER,
                channel INTEGER,
                base_value INTEGER DEFAULT 255,
                target_type TEXT DEFAULT 'channel',
                target_universe_id INTEGER,
                FOREIGN KEY (group_id) REFERENCES groups(id)
            )
        """)
        cursor.execute("""
            INSERT INTO group_members (id, group_id, universe_id, channel, base_value, target_type, target_universe_id)
            SELECT id, group_id, universe_id, channel, base_value,
                   COALESCE(target_type, 'channel'), target_universe_id
            FROM group_members_old
        """)
        cursor.execute("DROP TABLE group_members_old")
        conn.commit()

    # Add color_role column to group_members table for color mixer support
    cursor.execute("PRAGMA table_info(group_members)")
    member_columns = [col[1] for col in cursor.fetchall()]
    if 'color_role' not in member_columns:
        cursor.execute("ALTER TABLE group_members ADD COLUMN color_role TEXT DEFAULT NULL")
        conn.commit()

    # Create scene_master_values table for storing grandmaster values in scenes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scene_master_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            master_type TEXT NOT NULL,
            universe_id INTEGER,
            value INTEGER NOT NULL,
            FOREIGN KEY (scene_id) REFERENCES scenes(id)
        )
    """)
    conn.commit()

    # Create midi_cc_mappings table for MIDI CC -> Input Channel mappings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS midi_cc_mappings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cc_number INTEGER NOT NULL,
            midi_channel INTEGER DEFAULT -1,
            input_channel INTEGER NOT NULL,
            label TEXT DEFAULT '',
            enabled BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()

    # Create midi_triggers table for MIDI Note -> Action triggers
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS midi_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note INTEGER NOT NULL,
            midi_channel INTEGER DEFAULT -1,
            action TEXT NOT NULL,
            target_id INTEGER,
            label TEXT DEFAULT '',
            enabled BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()

    # Add device_name column to midi_cc_mappings (for multi-device support)
    cursor.execute("PRAGMA table_info(midi_cc_mappings)")
    cc_columns = [col[1] for col in cursor.fetchall()]
    if 'device_name' not in cc_columns:
        cursor.execute("ALTER TABLE midi_cc_mappings ADD COLUMN device_name TEXT DEFAULT NULL")
        conn.commit()

    # Remove universe_id from midi_cc_mappings (mappings now apply to all MIDI-input universes)
    cursor.execute("PRAGMA table_info(midi_cc_mappings)")
    cc_columns = [col[1] for col in cursor.fetchall()]
    if 'universe_id' in cc_columns:
        # Drop and recreate without universe_id
        cursor.execute("DROP TABLE IF EXISTS midi_cc_mappings")
        cursor.execute("""
            CREATE TABLE midi_cc_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cc_number INTEGER NOT NULL,
                midi_channel INTEGER DEFAULT -1,
                input_channel INTEGER NOT NULL,
                label TEXT DEFAULT '',
                enabled BOOLEAN DEFAULT 1,
                device_name TEXT DEFAULT NULL
            )
        """)
        conn.commit()

    # Add device_name column to midi_triggers (for multi-device support)
    cursor.execute("PRAGMA table_info(midi_triggers)")
    trigger_columns = [col[1] for col in cursor.fetchall()]
    if 'device_name' not in trigger_columns:
        cursor.execute("ALTER TABLE midi_triggers ADD COLUMN device_name TEXT DEFAULT NULL")
        conn.commit()

    # Create parked_channels table for storing channels locked to fixed values
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS parked_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            universe_id INTEGER NOT NULL,
            channel INTEGER NOT NULL,
            value INTEGER NOT NULL,
            FOREIGN KEY (universe_id) REFERENCES universes(id) ON DELETE CASCADE
        )
    """)
    conn.commit()

    conn.close()


def get_db():
    """Dependency for getting database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
