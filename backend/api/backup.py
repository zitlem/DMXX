"""Backup and restore API endpoints."""
import json
import os
import shutil
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..database import get_db, Backup, DATABASE_PATH
from ..auth import get_current_user

router = APIRouter()

BACKUP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "backups")


class CreateBackupRequest(BaseModel):
    comment: Optional[str] = ""


def backup_to_dict(backup: Backup) -> dict:
    """Convert a Backup model to dictionary."""
    return {
        "id": backup.id,
        "timestamp": backup.timestamp,
        "comment": backup.comment,
        "folder_path": backup.folder_path
    }


@router.get("/list")
async def list_backups(db: Session = Depends(get_db)):
    """List all backups."""
    backups = db.query(Backup).order_by(Backup.timestamp.desc()).all()
    return {"backups": [backup_to_dict(b) for b in backups]}


@router.post("/create")
async def create_backup(
    request: CreateBackupRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Create a new backup."""
    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # Generate timestamp and folder name
    timestamp = datetime.now().isoformat()
    folder_name = timestamp.replace(":", "-").replace(".", "-")
    folder_path = os.path.join(BACKUP_DIR, folder_name)

    os.makedirs(folder_path, exist_ok=True)

    try:
        # Copy database
        db_backup_path = os.path.join(folder_path, "database.db")
        shutil.copy2(DATABASE_PATH, db_backup_path)

        # Create metadata
        metadata = {
            "timestamp": timestamp,
            "comment": request.comment,
            "version": "1.0.0"
        }
        with open(os.path.join(folder_path, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)

        # Create config snapshot
        config = {
            "created_at": timestamp,
            "source_db": DATABASE_PATH
        }
        with open(os.path.join(folder_path, "config.json"), "w") as f:
            json.dump(config, f, indent=2)

        # Record backup in database
        backup = Backup(
            timestamp=timestamp,
            comment=request.comment or "",
            folder_path=folder_path
        )
        db.add(backup)
        db.commit()
        db.refresh(backup)

        return backup_to_dict(backup)

    except Exception as e:
        # Clean up on failure
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)
        raise HTTPException(status_code=500, detail=f"Backup failed: {str(e)}")


@router.post("/restore/{backup_id}")
async def restore_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Restore from a backup."""
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    if not os.path.exists(backup.folder_path):
        raise HTTPException(status_code=404, detail="Backup folder not found")

    backup_db_path = os.path.join(backup.folder_path, "database.db")
    if not os.path.exists(backup_db_path):
        raise HTTPException(status_code=404, detail="Backup database not found")

    try:
        # Close database connections (this is handled by SQLAlchemy session)
        db.close()

        # Create a pre-restore backup
        pre_restore_backup = os.path.join(BACKUP_DIR, "pre-restore-backup.db")
        if os.path.exists(DATABASE_PATH):
            shutil.copy2(DATABASE_PATH, pre_restore_backup)

        # Restore the database
        shutil.copy2(backup_db_path, DATABASE_PATH)

        return {
            "status": "restored",
            "backup_id": backup_id,
            "timestamp": backup.timestamp,
            "message": "Database restored. Please restart the application."
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.delete("/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_user)
):
    """Delete a backup."""
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    # Delete backup folder
    if os.path.exists(backup.folder_path):
        shutil.rmtree(backup.folder_path)

    # Remove from database
    db.delete(backup)
    db.commit()

    return {"status": "deleted", "backup_id": backup_id}


@router.get("/{backup_id}")
async def get_backup_info(
    backup_id: int,
    db: Session = Depends(get_db)
):
    """Get information about a specific backup."""
    backup = db.query(Backup).filter(Backup.id == backup_id).first()
    if not backup:
        raise HTTPException(status_code=404, detail="Backup not found")

    result = backup_to_dict(backup)

    # Add file info if exists
    if os.path.exists(backup.folder_path):
        metadata_path = os.path.join(backup.folder_path, "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                result["metadata"] = json.load(f)

        db_path = os.path.join(backup.folder_path, "database.db")
        if os.path.exists(db_path):
            result["size_bytes"] = os.path.getsize(db_path)

    return result
