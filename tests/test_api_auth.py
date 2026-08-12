"""API tests for login, IP whitelist and profile management."""
import pytest
from fastapi import HTTPException

from backend import auth as auth_module
from backend.api import auth as auth_api
from backend.config import AVAILABLE_PAGES
from backend.database import IPWhitelist, Profile


@pytest.fixture
def client(make_app):
    return make_app(auth_api.router, prefix="/api/auth")


@pytest.fixture
def viewer_client(make_app):
    """A client whose user is authenticated but not an admin."""
    return make_app(auth_api.router, prefix="/api/auth",
                    user={"is_admin": False, "profile_name": "Viewer"})


def add_profile(db, name="Admin", password="dmxx", is_admin=True, **extra):
    profile = Profile(name=name, password=password,
                      allowed_pages=extra.pop("allowed_pages", ["faders"]),
                      is_admin=is_admin, **extra)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def test_login_with_a_valid_password(client, db_session):
    add_profile(db_session, name="Tech", password="tech-pass", is_admin=False,
                allowed_pages=["faders", "scenes"])

    body = client.post("/api/auth/login", json={"password": "tech-pass"}).json()

    assert body["token_type"] == "bearer"
    assert body["profile_name"] == "Tech"
    assert body["allowed_pages"] == ["faders", "scenes"]
    assert body["is_admin"] is False
    assert auth_module.verify_token(body["access_token"])["profile_name"] == "Tech"


def test_login_with_a_bad_password(client, db_session):
    add_profile(db_session, password="dmxx")

    response = client.post("/api/auth/login", json={"password": "wrong"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect password"


def test_login_against_an_empty_profile_table(client):
    assert client.post("/api/auth/login",
                       json={"password": "anything"}).status_code == 401


def test_login_returns_permission_flags(client, db_session):
    add_profile(db_session, name="Limited", password="limited",
                can_park=False, can_highlight=False, can_bypass=False)

    body = client.post("/api/auth/login", json={"password": "limited"}).json()
    assert body["can_park"] is False
    assert body["can_highlight"] is False
    assert body["can_bypass"] is False


def test_login_defaults_null_permissions_to_true(client, db_session):
    profile = add_profile(db_session, name="Legacy", password="legacy")
    profile.can_park = None
    profile.can_highlight = None
    profile.can_bypass = None
    db_session.commit()

    body = client.post("/api/auth/login", json={"password": "legacy"}).json()
    assert body["can_park"] is True


def test_login_requires_a_password_field(client):
    assert client.post("/api/auth/login", json={}).status_code == 422


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def test_status_when_authenticated(client):
    body = client.get("/api/auth/status").json()
    assert body["authenticated"] is True
    assert body["profile_name"] == "Admin"
    assert body["is_admin"] is True
    assert "ip" in body


def test_status_when_not_authenticated(client):
    async def _anonymous():
        return None

    client.app.dependency_overrides[auth_module.optional_auth] = _anonymous

    body = client.get("/api/auth/status").json()
    assert body["authenticated"] is False
    assert set(body) == {"authenticated", "ip"}


def test_status_reports_the_forwarded_client_ip(client):
    body = client.get("/api/auth/status",
                      headers={"X-Forwarded-For": "203.0.113.9"}).json()
    assert body["ip"] == "203.0.113.9"


# ---------------------------------------------------------------------------
# Whitelist
# ---------------------------------------------------------------------------
def test_whitelist_is_empty_initially(client):
    assert client.get("/api/auth/whitelist").json() == {"whitelist": []}


def test_add_to_the_whitelist(client, db_session):
    response = client.post("/api/auth/whitelist", json={"ip_address": "10.0.0.1"})

    assert response.json() == {"status": "added", "ip": "10.0.0.1"}
    assert db_session.query(IPWhitelist).count() == 1
    assert client.get("/api/auth/whitelist").json() == {"whitelist": ["10.0.0.1"]}


def test_adding_a_duplicate_is_rejected(client):
    client.post("/api/auth/whitelist", json={"ip_address": "10.0.0.1"})

    response = client.post("/api/auth/whitelist", json={"ip_address": "10.0.0.1"})
    assert response.status_code == 400
    assert response.json()["detail"] == "IP already whitelisted"


def test_remove_from_the_whitelist(client, db_session):
    client.post("/api/auth/whitelist", json={"ip_address": "10.0.0.1"})

    assert client.delete("/api/auth/whitelist/10.0.0.1").json() == {
        "status": "removed", "ip": "10.0.0.1"}
    assert db_session.query(IPWhitelist).count() == 0


def test_removing_an_unknown_ip_is_404(client):
    response = client.delete("/api/auth/whitelist/10.0.0.9")
    assert response.status_code == 404
    assert response.json()["detail"] == "IP not found in whitelist"


# ---------------------------------------------------------------------------
# Profiles - listing
# ---------------------------------------------------------------------------
def test_list_profiles(client, db_session):
    add_profile(db_session, name="Admin", password="secret")
    add_profile(db_session, name="Booth", password=None, is_admin=False,
                ip_addresses=["10.0.0.5"])

    profiles = client.get("/api/auth/profiles").json()

    by_name = {p["name"]: p for p in profiles}
    assert by_name["Admin"]["has_password"] is True
    assert by_name["Booth"]["has_password"] is False
    assert by_name["Booth"]["ip_addresses"] == ["10.0.0.5"]
    assert all("password" not in p for p in profiles)


def test_listing_profiles_requires_admin(viewer_client):
    assert viewer_client.get("/api/auth/profiles").status_code == 403


# ---------------------------------------------------------------------------
# Profiles - creation
# ---------------------------------------------------------------------------
def test_create_a_password_profile(client, db_session):
    body = client.post("/api/auth/profiles", json={
        "name": "Tech", "password": "tech1234",
        "allowed_pages": ["faders"], "is_admin": False,
    }).json()

    assert body["name"] == "Tech"
    assert body["has_password"] is True
    assert body["is_admin"] is False
    assert db_session.query(Profile).count() == 1


def test_create_an_ip_only_profile(client):
    body = client.post("/api/auth/profiles", json={
        "name": "Booth", "ip_addresses": ["10.0.0.5"],
        "allowed_pages": ["faders"],
    }).json()

    assert body["has_password"] is False
    assert body["ip_addresses"] == ["10.0.0.5"]


def test_create_requires_an_auth_method(client):
    response = client.post("/api/auth/profiles",
                           json={"name": "Ghost", "allowed_pages": []})
    assert response.status_code == 400
    assert response.json()["detail"] == \
        "Profile must have either a password or IP addresses"


def test_create_rejects_a_duplicate_name(client, db_session):
    add_profile(db_session, name="Tech", password="one234")

    response = client.post("/api/auth/profiles", json={
        "name": "Tech", "password": "two234", "allowed_pages": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "Profile name already exists"


def test_create_rejects_a_short_password(client):
    response = client.post("/api/auth/profiles", json={
        "name": "Tech", "password": "abc", "allowed_pages": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "Password must be at least 4 characters"


def test_create_rejects_a_reused_password(client, db_session):
    add_profile(db_session, name="Admin", password="shared123")

    response = client.post("/api/auth/profiles", json={
        "name": "Other", "password": "shared123", "allowed_pages": []})
    assert response.status_code == 400
    assert response.json()["detail"] == "Password already used by another profile"


def test_create_stores_permission_flags(client):
    body = client.post("/api/auth/profiles", json={
        "name": "Limited", "password": "limited1",
        "allowed_pages": ["faders"], "can_park": False,
        "can_highlight": False, "can_bypass": False,
    }).json()

    assert (body["can_park"], body["can_highlight"], body["can_bypass"]) == \
        (False, False, False)


def test_create_requires_admin(viewer_client):
    response = viewer_client.post("/api/auth/profiles", json={
        "name": "Tech", "password": "tech1234", "allowed_pages": []})
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Profiles - update
# ---------------------------------------------------------------------------
def test_update_profile_fields(client, db_session):
    profile = add_profile(db_session, name="Tech", password="tech1234",
                          is_admin=False)
    add_profile(db_session, name="Admin", password="admin123")

    body = client.put(f"/api/auth/profiles/{profile.id}", json={
        "name": "Tech 2", "allowed_pages": ["faders", "io"],
        "allowed_grids": [1, 2], "allowed_scenes": [4],
    }).json()

    assert body["name"] == "Tech 2"
    assert body["allowed_pages"] == ["faders", "io"]
    assert body["allowed_grids"] == [1, 2]
    assert body["allowed_scenes"] == [4]


def test_update_can_change_the_password(client, db_session):
    profile = add_profile(db_session, name="Tech", password="old1234")

    client.put(f"/api/auth/profiles/{profile.id}", json={"password": "new1234"})
    db_session.expire_all()
    assert db_session.query(Profile).one().password == "new1234"


def test_update_rejects_a_short_password(client, db_session):
    profile = add_profile(db_session, name="Tech", password="old1234")
    response = client.put(f"/api/auth/profiles/{profile.id}",
                          json={"password": "ab"})
    assert response.status_code == 400


def test_update_rejects_a_password_used_elsewhere(client, db_session):
    add_profile(db_session, name="Other", password="taken123")
    profile = add_profile(db_session, name="Tech", password="mine1234")

    response = client.put(f"/api/auth/profiles/{profile.id}",
                          json={"password": "taken123"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Password already used by another profile"


def test_update_rejects_a_duplicate_name(client, db_session):
    add_profile(db_session, name="Taken", password="taken123")
    profile = add_profile(db_session, name="Tech", password="mine1234")

    response = client.put(f"/api/auth/profiles/{profile.id}",
                          json={"name": "Taken"})
    assert response.status_code == 400


def test_update_allows_keeping_the_same_name(client, db_session):
    profile = add_profile(db_session, name="Tech", password="mine1234")
    assert client.put(f"/api/auth/profiles/{profile.id}",
                      json={"name": "Tech"}).status_code == 200


def test_empty_lists_are_normalised_to_null(client, db_session):
    profile = add_profile(db_session, name="Tech", password="mine1234",
                          ip_addresses=["10.0.0.1"], allowed_grids=[1],
                          allowed_scenes=[1])

    body = client.put(f"/api/auth/profiles/{profile.id}", json={
        "allowed_grids": [], "allowed_scenes": []}).json()

    assert body["allowed_grids"] is None
    assert body["allowed_scenes"] is None


def test_update_cannot_strip_the_last_auth_method(client, db_session):
    profile = add_profile(db_session, name="Booth", password=None,
                          ip_addresses=["10.0.0.5"])

    response = client.put(f"/api/auth/profiles/{profile.id}",
                          json={"ip_addresses": []})
    assert response.status_code == 400
    assert "password or IP addresses" in response.json()["detail"]


def test_cannot_demote_the_last_admin(client, db_session):
    profile = add_profile(db_session, name="Admin", password="admin123")

    response = client.put(f"/api/auth/profiles/{profile.id}",
                          json={"is_admin": False})
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot remove last admin profile"


def test_can_demote_an_admin_when_another_exists(client, db_session):
    add_profile(db_session, name="Admin1", password="admin111")
    second = add_profile(db_session, name="Admin2", password="admin222")

    body = client.put(f"/api/auth/profiles/{second.id}",
                      json={"is_admin": False}).json()
    assert body["is_admin"] is False


def test_update_missing_profile_is_404(client):
    assert client.put("/api/auth/profiles/99", json={"name": "x"}).status_code == 404


def test_update_requires_admin(viewer_client, db_session):
    profile = add_profile(db_session, name="Tech", password="tech1234")
    assert viewer_client.put(f"/api/auth/profiles/{profile.id}",
                             json={"name": "x"}).status_code == 403


# ---------------------------------------------------------------------------
# Profiles - delete
# ---------------------------------------------------------------------------
def test_delete_a_non_admin_profile(client, db_session):
    add_profile(db_session, name="Admin", password="admin123")
    tech = add_profile(db_session, name="Tech", password="tech1234",
                       is_admin=False)

    assert client.delete(f"/api/auth/profiles/{tech.id}").json() == {
        "status": "deleted"}
    assert db_session.query(Profile).count() == 1


def test_cannot_delete_the_last_admin(client, db_session):
    admin = add_profile(db_session, name="Admin", password="admin123")

    response = client.delete(f"/api/auth/profiles/{admin.id}")
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot delete last admin profile"


def test_can_delete_an_admin_when_another_exists(client, db_session):
    add_profile(db_session, name="Admin1", password="admin111")
    second = add_profile(db_session, name="Admin2", password="admin222")

    assert client.delete(f"/api/auth/profiles/{second.id}").status_code == 200


def test_delete_missing_profile_is_404(client):
    assert client.delete("/api/auth/profiles/99").status_code == 404


def test_delete_requires_admin(viewer_client, db_session):
    profile = add_profile(db_session, name="Tech", password="tech1234",
                          is_admin=False)
    assert viewer_client.delete(
        f"/api/auth/profiles/{profile.id}").status_code == 403


# ---------------------------------------------------------------------------
# Page catalogue
# ---------------------------------------------------------------------------
def test_page_listing_is_public(client):
    assert client.get("/api/auth/pages").json() == {"pages": AVAILABLE_PAGES}
