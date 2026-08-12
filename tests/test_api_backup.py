"""API tests for backup creation, listing, restore and deletion."""
import json
import os

import pytest

from backend.api import backup as backup_api
from backend.database import Backup


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Redirect the backup directory and source database into tmp_path."""
    backup_dir = tmp_path / "backups"
    source_db = tmp_path / "source.db"
    source_db.write_bytes(b"SQLite format 3\x00original")

    monkeypatch.setattr(backup_api, "BACKUP_DIR", str(backup_dir))
    monkeypatch.setattr(backup_api, "DATABASE_PATH", str(source_db))
    return {"backup_dir": backup_dir, "source_db": source_db}


@pytest.fixture
def client(make_app, paths):
    return make_app(backup_api.router, prefix="/api/backup")


# ---------------------------------------------------------------------------
# Create & list
# ---------------------------------------------------------------------------
def test_list_is_empty_initially(client):
    assert client.get("/api/backup/list").json() == {"backups": []}


def test_create_a_backup(client, db_session, paths):
    body = client.post("/api/backup/create",
                       json={"comment": "before the show"}).json()

    assert body["comment"] == "before the show"
    assert os.path.isdir(body["folder_path"])
    assert db_session.query(Backup).count() == 1


def test_backup_folder_contains_the_database_and_metadata(client, paths):
    body = client.post("/api/backup/create", json={"comment": "x"}).json()
    folder = body["folder_path"]

    assert os.path.exists(os.path.join(folder, "database.db"))
    assert os.path.exists(os.path.join(folder, "config.json"))

    with open(os.path.join(folder, "metadata.json")) as handle:
        metadata = json.load(handle)
    assert metadata["comment"] == "x"
    assert metadata["version"] == "1.0.0"
    assert metadata["timestamp"] == body["timestamp"]


def test_the_copied_database_matches_the_source(client, paths):
    body = client.post("/api/backup/create", json={}).json()
    copied = os.path.join(body["folder_path"], "database.db")
    assert open(copied, "rb").read() == paths["source_db"].read_bytes()


def test_create_without_a_comment(client):
    assert client.post("/api/backup/create", json={}).json()["comment"] == ""


def test_backups_are_listed_newest_first(client, db_session):
    db_session.add_all([
        Backup(timestamp="2026-01-01T00:00:00", folder_path="/a"),
        Backup(timestamp="2026-06-01T00:00:00", folder_path="/b"),
    ])
    db_session.commit()

    stamps = [b["timestamp"] for b in
              client.get("/api/backup/list").json()["backups"]]
    assert stamps == ["2026-06-01T00:00:00", "2026-01-01T00:00:00"]


def test_create_fails_cleanly_when_the_source_is_missing(client, paths,
                                                         db_session):
    paths["source_db"].unlink()

    response = client.post("/api/backup/create", json={})

    assert response.status_code == 500
    assert "Backup failed" in response.json()["detail"]
    assert db_session.query(Backup).count() == 0
    assert list(paths["backup_dir"].iterdir()) == []


# ---------------------------------------------------------------------------
# Info
# ---------------------------------------------------------------------------
def test_backup_info_includes_metadata_and_size(client):
    created = client.post("/api/backup/create", json={"comment": "note"}).json()

    body = client.get(f"/api/backup/{created['id']}").json()

    assert body["comment"] == "note"
    assert body["metadata"]["comment"] == "note"
    assert body["size_bytes"] > 0


def test_backup_info_without_a_folder(client, db_session):
    db_session.add(Backup(timestamp="2026-01-01", folder_path="/does/not/exist"))
    db_session.commit()

    body = client.get("/api/backup/1").json()
    assert "metadata" not in body
    assert "size_bytes" not in body


def test_backup_info_missing_id_is_404(client):
    assert client.get("/api/backup/99").status_code == 404


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
def test_restore_overwrites_the_live_database(client, paths):
    created = client.post("/api/backup/create", json={}).json()
    paths["source_db"].write_bytes(b"SQLite format 3\x00changed")

    body = client.post(f"/api/backup/restore/{created['id']}").json()

    assert body["status"] == "restored"
    assert body["backup_id"] == created["id"]
    assert paths["source_db"].read_bytes() == b"SQLite format 3\x00original"


def test_restore_keeps_a_pre_restore_copy(client, paths):
    created = client.post("/api/backup/create", json={}).json()
    paths["source_db"].write_bytes(b"SQLite format 3\x00changed")

    client.post(f"/api/backup/restore/{created['id']}")

    pre_restore = paths["backup_dir"] / "pre-restore-backup.db"
    assert pre_restore.read_bytes() == b"SQLite format 3\x00changed"


def test_restore_missing_backup_is_404(client):
    assert client.post("/api/backup/restore/99").status_code == 404


def test_restore_missing_folder_is_404(client, db_session):
    db_session.add(Backup(timestamp="2026-01-01", folder_path="/does/not/exist"))
    db_session.commit()

    response = client.post("/api/backup/restore/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Backup folder not found"


def test_restore_missing_database_file_is_404(client, db_session, tmp_path):
    empty = tmp_path / "empty-backup"
    empty.mkdir()
    db_session.add(Backup(timestamp="2026-01-01", folder_path=str(empty)))
    db_session.commit()

    response = client.post("/api/backup/restore/1")
    assert response.status_code == 404
    assert response.json()["detail"] == "Backup database not found"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def test_delete_removes_the_row_and_the_folder(client, db_session):
    created = client.post("/api/backup/create", json={}).json()

    assert client.delete(f"/api/backup/{created['id']}").json() == {
        "status": "deleted", "backup_id": created["id"]}
    assert db_session.query(Backup).count() == 0
    assert not os.path.exists(created["folder_path"])


def test_delete_tolerates_a_missing_folder(client, db_session):
    db_session.add(Backup(timestamp="2026-01-01", folder_path="/does/not/exist"))
    db_session.commit()

    assert client.delete("/api/backup/1").status_code == 200
    assert db_session.query(Backup).count() == 0


def test_delete_missing_backup_is_404(client):
    assert client.delete("/api/backup/99").status_code == 404
