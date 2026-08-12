"""Tests for authentication: tokens, IP matching, profiles and access guards."""
import json
from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

from backend import auth
from backend.database import IPWhitelist, Profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_profile(db, name="Admin", password="dmxx", ip_addresses=None,
                 allowed_pages=None, is_admin=True, **extra):
    profile = Profile(
        name=name,
        password=password,
        ip_addresses=ip_addresses,
        allowed_pages=allowed_pages if allowed_pages is not None else ["faders"],
        is_admin=is_admin,
        **extra,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


class FakeRequest:
    def __init__(self, ip="127.0.0.1", headers=None):
        self.headers = headers or {}
        self.client = type("Client", (), {"host": ip})() if ip else None


class FakeCredentials:
    def __init__(self, token):
        self.credentials = token
        self.scheme = "Bearer"


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def test_verify_password():
    assert auth.verify_password("dmxx", "dmxx") is True
    assert auth.verify_password("dmxx", "other") is False
    assert auth.verify_password("", "") is True


def test_get_password_hash_is_plain_text_today():
    assert auth.get_password_hash("dmxx") == "dmxx"


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------
def test_load_config_reads_the_repository_config():
    config = auth.load_config()
    assert isinstance(config, dict)
    assert "password" in config


def test_load_config_falls_back_when_the_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "nope.json"))
    assert auth.load_config() == {
        "password": "dmxx",
        "secret_key": "dmxx-secret-key-change-in-production",
    }


def test_load_config_reads_a_custom_file(monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"password": "s3cret", "ip_whitelist": ["10.0.0.1"]}))
    monkeypatch.setattr(auth, "CONFIG_PATH", str(path))

    config = auth.load_config()
    assert config["password"] == "s3cret"
    assert config["ip_whitelist"] == ["10.0.0.1"]


# ---------------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------------
def test_create_and_verify_access_token():
    token = auth.create_access_token({"sub": "42"})
    payload = auth.verify_token(token)

    assert payload["sub"] == "42"
    assert "exp" in payload


def test_verify_token_rejects_garbage():
    assert auth.verify_token("not-a-token") is None
    assert auth.verify_token("") is None


def test_verify_token_rejects_a_foreign_signature():
    token = jwt.encode({"sub": "1"}, "some-other-key", algorithm="HS256")
    assert auth.verify_token(token) is None


def test_verify_token_rejects_an_expired_token():
    token = auth.create_access_token({"sub": "1"},
                                     expires_delta=timedelta(seconds=-10))
    assert auth.verify_token(token) is None


def test_profile_token_carries_permissions(db_session):
    profile = make_profile(db_session, name="Tech", allowed_pages=["faders", "io"],
                           is_admin=False, allowed_grids=[1], allowed_scenes=[2],
                           can_park=False)

    payload = auth.verify_token(auth.create_profile_token(profile))

    assert payload["sub"] == str(profile.id)
    assert payload["profile_name"] == "Tech"
    assert payload["allowed_pages"] == ["faders", "io"]
    assert payload["allowed_grids"] == [1]
    assert payload["allowed_scenes"] == [2]
    assert payload["is_admin"] is False
    assert payload["can_park"] is False
    assert payload["can_highlight"] is True


def test_profile_token_without_ips_expires_sooner(db_session):
    short = make_profile(db_session, name="NoIP")
    long = make_profile(db_session, name="WithIP", ip_addresses=["10.0.0.1"])

    short_exp = auth.verify_token(auth.create_profile_token(short))["exp"]
    long_exp = auth.verify_token(auth.create_profile_token(long))["exp"]

    assert long_exp - short_exp > 3600  # 24h vs 1h


def test_profile_token_honours_an_explicit_expiry(db_session):
    profile = make_profile(db_session, ip_addresses=["10.0.0.1"])
    token = auth.create_profile_token(profile, expires_delta=timedelta(seconds=-1))
    assert auth.verify_token(token) is None


def test_profile_token_defaults_null_permissions_to_true(db_session):
    profile = make_profile(db_session, name="Legacy")
    profile.can_park = None
    profile.can_highlight = None
    profile.can_bypass = None

    payload = auth.verify_token(auth.create_profile_token(profile))
    assert payload["can_park"] is True
    assert payload["can_highlight"] is True
    assert payload["can_bypass"] is True


# ---------------------------------------------------------------------------
# IP matching
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ip,pattern,expected", [
    ("192.168.1.5", "192.168.1.5", True),
    ("192.168.1.5", "192.168.1.6", False),
    ("192.168.1.5", "192.168.1.*", True),
    ("192.168.2.5", "192.168.1.*", False),
    ("192.168.15.5", "192.168.1.*", False),  # not a prefix-only match
    ("10.0.0.1", "*", False),
])
def test_ip_matches(ip, pattern, expected):
    assert auth.ip_matches(ip, pattern) is expected


def test_get_client_ip_from_the_socket():
    assert auth.get_client_ip(FakeRequest(ip="10.0.0.9")) == "10.0.0.9"


def test_get_client_ip_prefers_the_forwarded_header():
    request = FakeRequest(ip="10.0.0.9",
                          headers={"X-Forwarded-For": "203.0.113.5, 10.0.0.1"})
    assert auth.get_client_ip(request) == "203.0.113.5"


def test_get_client_ip_without_a_client():
    assert auth.get_client_ip(FakeRequest(ip=None)) == "unknown"


# ---------------------------------------------------------------------------
# Whitelists
# ---------------------------------------------------------------------------
def test_database_whitelist_crud(db_session):
    assert auth.add_ip_to_whitelist("10.0.0.1", db_session) is True
    assert auth.add_ip_to_whitelist("10.0.0.1", db_session) is False  # duplicate
    assert auth.get_whitelist(db_session) == ["10.0.0.1"]

    assert auth.remove_ip_from_whitelist("10.0.0.1", db_session) is True
    assert auth.remove_ip_from_whitelist("10.0.0.1", db_session) is False
    assert auth.get_whitelist(db_session) == []


def test_is_ip_whitelisted_via_the_database(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    db_session.add(IPWhitelist(ip_address="10.0.0.1"))
    db_session.commit()

    assert auth.is_ip_whitelisted("10.0.0.1", db_session) is True
    assert auth.is_ip_whitelisted("10.0.0.2", db_session) is False


def test_is_ip_whitelisted_supports_database_wildcards(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    db_session.add(IPWhitelist(ip_address="192.168.1.*"))
    db_session.commit()

    assert auth.is_ip_whitelisted("192.168.1.77", db_session) is True
    assert auth.is_ip_whitelisted("192.168.2.77", db_session) is False


def test_is_ip_whitelisted_via_the_config_file(db_session, monkeypatch, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ip_whitelist": ["203.0.113.7", "10.1.*"]}))
    monkeypatch.setattr(auth, "CONFIG_PATH", str(path))

    assert auth.is_ip_whitelisted("203.0.113.7", db_session) is True
    assert auth.is_ip_whitelisted("10.1.2.3", db_session) is True
    assert auth.is_ip_whitelisted("10.2.2.3", db_session) is False


# ---------------------------------------------------------------------------
# Profile lookup by IP
# ---------------------------------------------------------------------------
def test_get_profile_by_ip_exact_match(db_session):
    make_profile(db_session, name="Booth", ip_addresses=["10.0.0.5"])
    assert auth.get_profile_by_ip("10.0.0.5", db_session).name == "Booth"


def test_get_profile_by_ip_wildcard_match(db_session):
    make_profile(db_session, name="Floor", ip_addresses=["10.0.0.*"])
    assert auth.get_profile_by_ip("10.0.0.77", db_session).name == "Floor"


def test_exact_matches_beat_wildcards(db_session):
    make_profile(db_session, name="Wild", ip_addresses=["10.0.0.*"])
    make_profile(db_session, name="Exact", ip_addresses=["10.0.0.5"])

    assert auth.get_profile_by_ip("10.0.0.5", db_session).name == "Exact"


def test_get_profile_by_ip_returns_none_when_nothing_matches(db_session):
    make_profile(db_session, name="Booth", ip_addresses=["10.0.0.5"])
    assert auth.get_profile_by_ip("192.168.0.1", db_session) is None


def test_profiles_without_ips_are_skipped(db_session):
    make_profile(db_session, name="NoIP", ip_addresses=None)
    assert auth.get_profile_by_ip("10.0.0.5", db_session) is None


# ---------------------------------------------------------------------------
# Password authentication
# ---------------------------------------------------------------------------
def test_authenticate_user_matches_a_profile_password(db_session):
    make_profile(db_session, name="Admin", password="dmxx")
    make_profile(db_session, name="Tech", password="tech-pass")

    assert auth.authenticate_user("tech-pass", db_session).name == "Tech"
    assert auth.authenticate_user("nope", db_session) is None


def test_authenticate_user_ignores_passwordless_profiles(db_session):
    make_profile(db_session, name="IPOnly", password=None)
    assert auth.authenticate_user("", db_session) is None


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_token_authentication_wins(db_session):
    profile = make_profile(db_session, name="Tech", allowed_pages=["faders"],
                           is_admin=False)
    credentials = FakeCredentials(auth.create_profile_token(profile))

    user = await auth.get_current_user(FakeRequest("10.0.0.99"), credentials,
                                       db_session)

    assert user["method"] == "token"
    assert user["profile_name"] == "Tech"
    assert user["allowed_pages"] == ["faders"]
    assert user["is_admin"] is False
    assert user["ip"] == "10.0.0.99"


@pytest.mark.asyncio
async def test_token_takes_priority_over_ip_profile(db_session):
    make_profile(db_session, name="ByIP", ip_addresses=["10.0.0.99"])
    token_profile = make_profile(db_session, name="ByToken")
    credentials = FakeCredentials(auth.create_profile_token(token_profile))

    user = await auth.get_current_user(FakeRequest("10.0.0.99"), credentials,
                                       db_session)
    assert user["profile_name"] == "ByToken"


@pytest.mark.asyncio
async def test_ip_profile_authentication(db_session):
    make_profile(db_session, name="Booth", ip_addresses=["10.0.0.5"],
                 allowed_pages=["faders", "scenes"], is_admin=False)

    user = await auth.get_current_user(FakeRequest("10.0.0.5"), None, db_session)

    assert user["method"] == "ip_profile"
    assert user["profile_name"] == "Booth"
    assert user["allowed_pages"] == ["faders", "scenes"]


@pytest.mark.asyncio
async def test_legacy_ip_whitelist_grants_admin(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    db_session.add(IPWhitelist(ip_address="10.0.0.7"))
    db_session.commit()

    user = await auth.get_current_user(FakeRequest("10.0.0.7"), None, db_session)

    assert user["method"] == "ip_whitelist"
    assert user["is_admin"] is True
    assert user["allowed_grids"] is None


@pytest.mark.asyncio
async def test_unauthenticated_request_is_rejected(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))

    with pytest.raises(HTTPException) as exc:
        await auth.get_current_user(FakeRequest("203.0.113.1"), None, db_session)

    assert exc.value.status_code == 401
    assert exc.value.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_token_falls_through_to_rejection(db_session, monkeypatch,
                                                        tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))

    with pytest.raises(HTTPException):
        await auth.get_current_user(FakeRequest("203.0.113.1"),
                                    FakeCredentials("bogus"), db_session)


@pytest.mark.asyncio
async def test_optional_auth_returns_none_instead_of_raising(db_session, monkeypatch,
                                                             tmp_path):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    assert await auth.optional_auth(FakeRequest("203.0.113.1"), None,
                                    db_session) is None


@pytest.mark.asyncio
async def test_optional_auth_returns_the_user_when_authenticated(db_session):
    profile = make_profile(db_session, name="Tech")
    credentials = FakeCredentials(auth.create_profile_token(profile))

    user = await auth.optional_auth(FakeRequest(), credentials, db_session)
    assert user["profile_name"] == "Tech"


# ---------------------------------------------------------------------------
# Access guards
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_require_page_access_allows_permitted_pages():
    guard = auth.require_page_access("scenes")
    user = {"allowed_pages": ["faders", "scenes"]}
    assert await guard(user) is user


@pytest.mark.asyncio
async def test_require_page_access_blocks_other_pages():
    guard = auth.require_page_access("settings")

    with pytest.raises(HTTPException) as exc:
        await guard({"allowed_pages": ["faders"]})

    assert exc.value.status_code == 403
    assert "settings" in exc.value.detail


@pytest.mark.asyncio
async def test_require_page_access_blocks_users_without_pages():
    guard = auth.require_page_access("faders")
    with pytest.raises(HTTPException):
        await guard({})


@pytest.mark.asyncio
async def test_require_admin_allows_admins():
    guard = auth.require_admin()
    user = {"is_admin": True}
    assert await guard(user) is user


@pytest.mark.asyncio
async def test_require_admin_blocks_everyone_else():
    guard = auth.require_admin()

    with pytest.raises(HTTPException) as exc:
        await guard({"is_admin": False})
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException):
        await guard({})


# ---------------------------------------------------------------------------
# Wildcard whitelist matching (regression: prefix match was not octet-aligned)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("ip,allowed", [
    ("192.168.1.5", True),
    ("192.168.1.255", True),
    ("192.168.11.5", False),    # neighbouring /24, must not match
    ("192.168.100.7", False),
    ("192.168.2.5", False),
])
def test_config_whitelist_wildcards_are_octet_aligned(db_session, monkeypatch,
                                                      tmp_path, ip, allowed):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"ip_whitelist": ["192.168.1.*"]}))
    monkeypatch.setattr(auth, "CONFIG_PATH", str(path))

    assert auth.is_ip_whitelisted(ip, db_session) is allowed


@pytest.mark.parametrize("ip,allowed", [
    ("10.0.0.9", True),
    ("10.0.09.9", False),
    ("10.0.99.9", False),
])
def test_database_whitelist_wildcards_are_octet_aligned(db_session, monkeypatch,
                                                        tmp_path, ip, allowed):
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    db_session.add(IPWhitelist(ip_address="10.0.0.*"))
    db_session.commit()

    assert auth.is_ip_whitelisted(ip, db_session) is allowed


def test_whitelist_matching_agrees_with_ip_matches(db_session, monkeypatch,
                                                   tmp_path):
    """The whitelist and the profile-IP matcher must not disagree."""
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    pattern = "172.16.5.*"
    db_session.add(IPWhitelist(ip_address=pattern))
    db_session.commit()

    for ip in ("172.16.5.1", "172.16.50.1", "172.16.5.200", "172.16.55.9"):
        assert auth.is_ip_whitelisted(ip, db_session) == auth.ip_matches(ip, pattern)


@pytest.mark.asyncio
async def test_a_neighbouring_subnet_is_not_authenticated(db_session, monkeypatch,
                                                          tmp_path):
    """End to end: the over-broad match must not grant admin access."""
    monkeypatch.setattr(auth, "CONFIG_PATH", str(tmp_path / "none.json"))
    db_session.add(IPWhitelist(ip_address="192.168.1.*"))
    db_session.commit()

    granted = await auth.get_current_user(FakeRequest("192.168.1.50"), None,
                                          db_session)
    assert granted["method"] == "ip_whitelist"

    with pytest.raises(HTTPException):
        await auth.get_current_user(FakeRequest("192.168.11.50"), None, db_session)
