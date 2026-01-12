"""Authentication API endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, Profile
from ..auth import (
    authenticate_user, create_access_token, create_profile_token,
    add_ip_to_whitelist, remove_ip_from_whitelist, get_whitelist,
    get_current_user, get_client_ip, optional_auth, require_admin, verify_password
)

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    profile_name: str
    allowed_pages: List[str]
    is_admin: bool


class IPRequest(BaseModel):
    ip_address: str


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with password and receive JWT token."""
    profile = authenticate_user(request.password, db)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_profile_token(profile)
    return LoginResponse(
        access_token=access_token,
        profile_name=profile.name,
        allowed_pages=profile.allowed_pages,
        is_admin=profile.is_admin
    )


@router.get("/status")
async def auth_status(
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(optional_auth)
):
    """Check authentication status and return client info with profile details."""
    client_ip = get_client_ip(request)

    if user:
        return {
            "authenticated": True,
            "method": user.get("method"),
            "ip": client_ip,
            "profile_name": user.get("profile_name"),
            "allowed_pages": user.get("allowed_pages", []),
            "is_admin": user.get("is_admin", False)
        }

    return {
        "authenticated": False,
        "ip": client_ip
    }


@router.get("/whitelist")
async def list_whitelist(
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Get all whitelisted IP addresses."""
    return {"whitelist": get_whitelist(db)}


@router.post("/whitelist")
async def add_whitelist(
    request: IPRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Add an IP address to the whitelist."""
    success = add_ip_to_whitelist(request.ip_address, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="IP already whitelisted"
        )
    return {"status": "added", "ip": request.ip_address}


@router.delete("/whitelist/{ip_address}")
async def remove_whitelist(
    ip_address: str,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Remove an IP address from the whitelist."""
    success = remove_ip_from_whitelist(ip_address, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="IP not found in whitelist"
        )
    return {"status": "removed", "ip": ip_address}


# ============= Profile Management Endpoints =============

class ProfileCreate(BaseModel):
    name: str
    password: Optional[str] = None
    ip_addresses: Optional[List[str]] = None
    allowed_pages: List[str]
    is_admin: bool = False


class ProfileUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    ip_addresses: Optional[List[str]] = None
    allowed_pages: Optional[List[str]] = None
    is_admin: Optional[bool] = None


class ProfileResponse(BaseModel):
    id: int
    name: str
    has_password: bool
    ip_addresses: Optional[List[str]]
    allowed_pages: List[str]
    is_admin: bool


@router.get("/profiles", response_model=List[ProfileResponse])
async def list_profiles(
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin())
):
    """List all profiles (admin only)."""
    profiles = db.query(Profile).all()
    return [
        ProfileResponse(
            id=p.id,
            name=p.name,
            has_password=bool(p.password),
            ip_addresses=p.ip_addresses,
            allowed_pages=p.allowed_pages,
            is_admin=p.is_admin
        )
        for p in profiles
    ]


@router.post("/profiles", response_model=ProfileResponse)
async def create_profile(
    data: ProfileCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin())
):
    """Create a new profile (admin only)."""
    # Must have password or IP addresses
    if not data.password and not data.ip_addresses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile must have either a password or IP addresses"
        )

    # Check for duplicate name
    existing = db.query(Profile).filter(Profile.name == data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile name already exists"
        )

    # Validate password if provided
    if data.password:
        if len(data.password) < 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 4 characters"
            )
        # Check for duplicate password
        for profile in db.query(Profile).all():
            if profile.password and verify_password(data.password, profile.password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password already used by another profile"
                )

    profile = Profile(
        name=data.name,
        password=data.password,
        ip_addresses=data.ip_addresses,
        allowed_pages=data.allowed_pages,
        is_admin=data.is_admin
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        has_password=bool(profile.password),
        ip_addresses=profile.ip_addresses,
        allowed_pages=profile.allowed_pages,
        is_admin=profile.is_admin
    )


@router.put("/profiles/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: int,
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin())
):
    """Update a profile (admin only)."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    if data.name is not None:
        existing = db.query(Profile).filter(
            Profile.name == data.name,
            Profile.id != profile_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile name already exists"
            )
        profile.name = data.name

    if data.password is not None:
        if len(data.password) < 4:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password must be at least 4 characters"
            )
        # Check for duplicate password
        for p in db.query(Profile).filter(Profile.id != profile_id).all():
            if p.password and verify_password(data.password, p.password):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Password already used by another profile"
                )
        profile.password = data.password

    if data.ip_addresses is not None:
        profile.ip_addresses = data.ip_addresses if data.ip_addresses else None

    if data.allowed_pages is not None:
        profile.allowed_pages = data.allowed_pages

    if data.is_admin is not None:
        # Prevent removing last admin
        if not data.is_admin and profile.is_admin:
            admin_count = db.query(Profile).filter(Profile.is_admin == True).count()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot remove last admin profile"
                )
        profile.is_admin = data.is_admin

    # Validate that profile still has at least one auth method
    if not profile.password and not profile.ip_addresses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile must have either a password or IP addresses"
        )

    db.commit()
    db.refresh(profile)

    return ProfileResponse(
        id=profile.id,
        name=profile.name,
        has_password=bool(profile.password),
        ip_addresses=profile.ip_addresses,
        allowed_pages=profile.allowed_pages,
        is_admin=profile.is_admin
    )


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin())
):
    """Delete a profile (admin only)."""
    profile = db.query(Profile).filter(Profile.id == profile_id).first()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )

    # Prevent deleting last admin
    if profile.is_admin:
        admin_count = db.query(Profile).filter(Profile.is_admin == True).count()
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete last admin profile"
            )

    db.delete(profile)
    db.commit()
    return {"status": "deleted"}


@router.get("/pages")
async def list_available_pages():
    """List all available pages for profile configuration."""
    return {
        "pages": [
            {"id": "faders", "name": "Faders"},
            {"id": "scenes", "name": "Scenes"},
            {"id": "fixtures", "name": "Fixtures"},
            {"id": "patch", "name": "Patch"},
            {"id": "io", "name": "I/O"},
            {"id": "groups", "name": "Groups"},
            {"id": "settings", "name": "Settings"}
        ]
    }
