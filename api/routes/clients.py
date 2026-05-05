from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from api.deps import get_db, get_accessible_client, get_current_user, require_client_admin, require_super_admin
from core.client_offboard import build_export_zip, purge_client
from core.config import settings
from core.models import Client, Domain, User, UserRole
from core.schemas.client import (
    ClientCreate, ClientUpdate, ClientMfaPolicyUpdate, ClientRead,
    ClientPurgeRequest, ClientPurgeResponse,
    DomainCreate, DomainRead,
)

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientRead])
def list_clients(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role == UserRole.super_admin:
        return db.query(Client).all()
    assigned_ids = {uc.client_id for uc in current_user.user_clients}
    return db.query(Client).filter(Client.id.in_(assigned_ids)).all()


@router.post("", response_model=ClientRead, status_code=status.HTTP_201_CREATED)
def create_client(body: ClientCreate, db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    if db.query(Client).filter_by(slug=body.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Client slug already exists")
    client = Client(slug=body.slug, name=body.name)
    db.add(client)
    db.commit()
    db.refresh(client)
    settings.client_incoming_dir(body.slug).mkdir(parents=True, exist_ok=True)
    return client


@router.get("/{slug}", response_model=ClientRead)
def get_client(slug: str, client: Client = Depends(get_accessible_client)):
    return client


@router.patch("/{slug}", response_model=ClientRead)
def update_client(
    slug: str,
    body: ClientUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    client = db.query(Client).filter_by(slug=slug).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if body.name is not None:
        client.name = body.name
    if body.is_active is not None:
        client.is_active = body.is_active
    db.commit()
    db.refresh(client)
    return client


@router.post("/{slug}/export")
def export_client(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    client = db.query(Client).filter_by(slug=slug).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    zip_bytes = build_export_zip(client, db)
    filename = f"{slug}-export-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{slug}", response_model=ClientPurgeResponse)
def delete_client(
    slug: str,
    body: ClientPurgeRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    client = db.query(Client).filter_by(slug=slug).first()
    if not client:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    if body.confirm_slug != slug:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="confirm_slug does not match client slug",
        )
    return purge_client(client, db)


@router.patch("/{slug}/mfa-policy", response_model=ClientRead)
def update_mfa_policy(
    slug: str,
    body: ClientMfaPolicyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    if body.mfa_required_admins is not None:
        client.mfa_required_admins = body.mfa_required_admins
    if body.mfa_required_viewers is not None:
        client.mfa_required_viewers = body.mfa_required_viewers
    db.commit()
    db.refresh(client)
    return client


# ── Domains ──────────────────────────────────────────────────────────────────

@router.get("/{slug}/domains", response_model=list[DomainRead])
def list_domains(slug: str, db: Session = Depends(get_db), client: Client = Depends(get_accessible_client)):
    return db.query(Domain).filter_by(client_id=client.id).all()


@router.post("/{slug}/domains", response_model=DomainRead, status_code=status.HTTP_201_CREATED)
def add_domain(
    slug: str,
    body: DomainCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    if db.query(Domain).filter_by(client_id=client.id, domain=body.domain).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Domain already registered for this client")
    domain = Domain(client_id=client.id, domain=body.domain)
    db.add(domain)
    db.commit()
    db.refresh(domain)
    return domain


@router.delete("/{slug}/domains/{domain_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_domain(
    slug: str,
    domain_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    domain = db.query(Domain).filter_by(id=domain_id, client_id=client.id).first()
    if not domain:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Domain not found")
    domain.is_active = False
    db.commit()


# ── Geo enrichment ────────────────────────────────────────────────────────────

@router.post("/{slug}/enrich-geo")
def trigger_geo_enrichment(
    slug: str,
    force: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    from ingestion.geo_enrichment import enrich_geo
    return enrich_geo(db, client.id, force=force)


@router.post("/{slug}/enrich-whois")
def trigger_whois_enrichment(
    slug: str,
    force: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    from ingestion.whois_enrichment import enrich_whois
    return enrich_whois(db, client.id, force=force)