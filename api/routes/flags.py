from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.deps import get_db, get_accessible_client, get_current_user
from core.models import Client, Flag, User
from core.schemas.flag import FlagRead, FlagAcknowledge, PaginatedFlags

router = APIRouter(prefix="/clients/{slug}/flags", tags=["flags"])
SEVERITIES = {"critical", "high", "medium", "low", "info"}


@router.get("", response_model=PaginatedFlags)
def list_flags(
    slug: str,
    severity: str | None = Query(None),
    flag_type: str | None = Query(None, max_length=64),
    unacknowledged_only: bool = Query(False),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    q = db.query(Flag).filter_by(client_id=client.id)
    if severity:
        if severity not in SEVERITIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Invalid severity '{severity}'")
        q = q.filter(Flag.severity == severity)
    if flag_type:
        q = q.filter(Flag.flag_type == flag_type)
    if unacknowledged_only:
        q = q.filter(Flag.acknowledged_at.is_(None))

    total = q.count()
    flags = q.order_by(Flag.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedFlags(total=total, page=page, page_size=page_size, items=flags)


@router.get("/{flag_id}", response_model=FlagRead)
def get_flag(
    slug: str,
    flag_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    flag = db.query(Flag).filter_by(id=flag_id, client_id=client.id).first()
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    return flag


@router.post("/{flag_id}/acknowledge", response_model=FlagRead)
def acknowledge_flag(
    slug: str,
    flag_id: int,
    body: FlagAcknowledge,
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
    current_user: User = Depends(get_current_user),
):
    flag = db.query(Flag).filter_by(id=flag_id, client_id=client.id).first()
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    flag.acknowledged_at = datetime.now(timezone.utc)
    flag.acknowledged_by = current_user.email
    db.commit()
    db.refresh(flag)
    return flag


@router.post("/{flag_id}/unacknowledge", response_model=FlagRead)
def unacknowledge_flag(
    slug: str,
    flag_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    flag = db.query(Flag).filter_by(id=flag_id, client_id=client.id).first()
    if not flag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Flag not found")
    flag.acknowledged_at = None
    flag.acknowledged_by = None
    db.commit()
    db.refresh(flag)
    return flag