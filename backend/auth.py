"""
Authentication system with password protection and IP whitelist bypass.
"""
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session
from .database import get_db, User, IPWhitelist, Setting, Profile

# Load config from file
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

def load_config():
    """Load configuration from config.json."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {"password": "dmxx", "secret_key": "dmxx-secret-key-change-in-production"}

_config = load_config()

# Security configuration
SECRET_KEY = _config.get("secret_key", "dmxx-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours for IP-whitelisted users
ACCESS_TOKEN_EXPIRE_MINUTES_NO_IP = 60  # 1 hour for non-IP-whitelisted users

security = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, stored_password: str) -> bool:
    """Verify a password (plain text for now)."""
    return plain_password == stored_password


def get_password_hash(password: str) -> str:
    """Store password (plain text for now)."""
    return password


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_profile_token(profile: Profile, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token with profile information.

    Token expires in 1 hour for profiles without IP whitelist,
    or 24 hours for profiles with IP addresses configured.
    """
    to_encode = {
        "sub": str(profile.id),
        "profile_name": profile.name,
        "allowed_pages": profile.allowed_pages,
        "is_admin": profile.is_admin
    }
    # Use shorter expiration if profile has no IP addresses (password-only login)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    elif profile.ip_addresses and len(profile.ip_addresses) > 0:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES_NO_IP)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_token(token: str) -> Optional[dict]:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def is_ip_whitelisted(ip_address: str, db: Session) -> bool:
    """Check if an IP address is whitelisted."""
    # Check config file whitelist first
    config = load_config()
    config_whitelist = config.get("ip_whitelist", [])
    for entry in config_whitelist:
        if entry == ip_address:
            return True
        # Support simple wildcard (e.g., 192.168.1.*)
        if entry.endswith(".*"):
            prefix = entry[:-2]
            if ip_address.startswith(prefix):
                return True

    # Check database whitelist
    db_whitelist = db.query(IPWhitelist).all()
    for entry in db_whitelist:
        if entry.ip_address == ip_address:
            return True
        if entry.ip_address.endswith(".*"):
            prefix = entry.ip_address[:-2]
            if ip_address.startswith(prefix):
                return True
    return False


def get_client_ip(request: Request) -> str:
    """Get the client's IP address from the request."""
    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ip_matches(client_ip: str, pattern: str) -> bool:
    """Check if IP matches pattern (supports * wildcard)."""
    if pattern == client_ip:
        return True
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return client_ip.startswith(prefix + ".")
    return False


def get_profile_by_ip(client_ip: str, db: Session) -> Optional[Profile]:
    """Find a profile that has this IP in its ip_addresses list.
    Prioritizes exact matches over wildcard matches."""
    profiles = db.query(Profile).all()

    # First pass: check for exact IP matches
    for profile in profiles:
        if profile.ip_addresses:
            for ip_pattern in profile.ip_addresses:
                if ip_pattern == client_ip:
                    return profile

    # Second pass: check for wildcard matches
    for profile in profiles:
        if profile.ip_addresses:
            for ip_pattern in profile.ip_addresses:
                if ip_pattern != client_ip and ip_matches(client_ip, ip_pattern):
                    return profile

    return None


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    """
    Authenticate the current user.
    Returns user info if authenticated, raises HTTPException otherwise.
    Priority: 1) JWT token (explicit login), 2) Profile IP match, 3) Old IP whitelist (legacy)
    """
    client_ip = get_client_ip(request)

    # Check for JWT token FIRST - explicit login takes priority over IP matching
    if credentials:
        payload = verify_token(credentials.credentials)
        if payload:
            return {
                "authenticated": True,
                "method": "token",
                "ip": client_ip,
                "profile_id": payload.get("sub"),
                "profile_name": payload.get("profile_name", "Unknown"),
                "allowed_pages": payload.get("allowed_pages", []),
                "is_admin": payload.get("is_admin", False)
            }

    # Check if any profile has this IP configured
    ip_profile = get_profile_by_ip(client_ip, db)
    if ip_profile:
        return {
            "authenticated": True,
            "method": "ip_profile",
            "ip": client_ip,
            "profile_id": ip_profile.id,
            "profile_name": ip_profile.name,
            "allowed_pages": ip_profile.allowed_pages,
            "is_admin": ip_profile.is_admin
        }

    # Legacy: Check old IP whitelist - grants full admin access
    if is_ip_whitelisted(client_ip, db):
        return {
            "authenticated": True,
            "method": "ip_whitelist",
            "ip": client_ip,
            "profile_id": None,
            "profile_name": "Admin",
            "allowed_pages": ["faders", "scenes", "fixtures", "patch", "io", "groups", "settings"],
            "is_admin": True
        }

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def optional_auth(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[dict]:
    """
    Optional authentication - returns None if not authenticated instead of raising.
    """
    try:
        return await get_current_user(request, credentials, db)
    except HTTPException:
        return None


def authenticate_user(password: str, db: Session) -> Optional[Profile]:
    """
    Authenticate by password - returns the matching profile or None.
    Checks all profiles for a matching password.
    """
    profiles = db.query(Profile).all()
    for profile in profiles:
        if profile.password and verify_password(password, profile.password):
            return profile
    return None


def add_ip_to_whitelist(ip_address: str, db: Session) -> bool:
    """Add an IP address to the whitelist."""
    existing = db.query(IPWhitelist).filter(IPWhitelist.ip_address == ip_address).first()
    if existing:
        return False

    entry = IPWhitelist(ip_address=ip_address)
    db.add(entry)
    db.commit()
    return True


def remove_ip_from_whitelist(ip_address: str, db: Session) -> bool:
    """Remove an IP address from the whitelist."""
    entry = db.query(IPWhitelist).filter(IPWhitelist.ip_address == ip_address).first()
    if entry:
        db.delete(entry)
        db.commit()
        return True
    return False


def get_whitelist(db: Session) -> list:
    """Get all whitelisted IP addresses."""
    return [entry.ip_address for entry in db.query(IPWhitelist).all()]


def require_page_access(page: str):
    """Dependency factory to require access to a specific page."""
    async def check_access(user: dict = Depends(get_current_user)):
        if page not in user.get("allowed_pages", []):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied to {page}"
            )
        return user
    return check_access


def require_admin():
    """Dependency to require admin access for profile management."""
    async def check_admin(user: dict = Depends(get_current_user)):
        if not user.get("is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        return user
    return check_admin
