import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

from api.deps import get_db, get_accessible_client, require_client_admin
from core.crypto import encrypt
from core.models import Client, ImapConfig, User
from core.schemas.imap import ImapConfigCreate, ImapConfigRead, ImapConfigUpdate, PollResult

router = APIRouter(prefix="/clients/{slug}/imap", tags=["imap"])


def _get_or_404(client_id: int, db: Session) -> ImapConfig:
    config = db.query(ImapConfig).filter_by(client_id=client_id).first()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No IMAP config for this client")
    return config


@router.get("", response_model=ImapConfigRead)
def get_imap_config(slug: str, db: Session = Depends(get_db), client: Client = Depends(get_accessible_client)):
    return _get_or_404(client.id, db)


@router.post("", response_model=ImapConfigRead, status_code=status.HTTP_201_CREATED)
def create_imap_config(
    slug: str,
    body: ImapConfigCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    if db.query(ImapConfig).filter_by(client_id=client.id).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="IMAP config already exists — use PATCH to update")

    if body.auth_type == "office365":
        config = ImapConfig(
            client_id=client.id,
            auth_type="office365",
            host="outlook.office365.com",
            port=993,
            use_ssl=True,
            username=body.username,
            encrypted_password=None,
            inbox_folder=body.inbox_folder,
            processed_folder=body.processed_folder,
            poll_interval_minutes=body.poll_interval_minutes,
            oauth2_tenant_id=body.oauth2_tenant_id,
            oauth2_client_id=body.oauth2_client_id,
            oauth2_client_secret=encrypt(body.oauth2_client_secret),
        )
    else:
        config = ImapConfig(
            client_id=client.id,
            auth_type="imap",
            host=body.host,
            port=body.port,
            use_ssl=body.use_ssl,
            username=body.username,
            encrypted_password=encrypt(body.password),
            inbox_folder=body.inbox_folder,
            processed_folder=body.processed_folder,
            poll_interval_minutes=body.poll_interval_minutes,
        )

    db.add(config)
    db.commit()
    db.refresh(config)
    _reschedule()
    return config


@router.patch("", response_model=ImapConfigRead)
def update_imap_config(
    slug: str,
    body: ImapConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    config = _get_or_404(client.id, db)
    # Common fields
    if body.username is not None: config.username = body.username
    if body.inbox_folder is not None: config.inbox_folder = body.inbox_folder
    if body.processed_folder is not None: config.processed_folder = body.processed_folder
    if body.poll_interval_minutes is not None: config.poll_interval_minutes = body.poll_interval_minutes
    if body.is_active is not None: config.is_active = body.is_active
    # Standard IMAP fields
    if body.host is not None: config.host = body.host
    if body.port is not None: config.port = body.port
    if body.use_ssl is not None: config.use_ssl = body.use_ssl
    if body.password is not None: config.encrypted_password = encrypt(body.password)
    # Office 365 OAuth2 fields
    if body.oauth2_tenant_id is not None: config.oauth2_tenant_id = body.oauth2_tenant_id
    if body.oauth2_client_id is not None: config.oauth2_client_id = body.oauth2_client_id
    if body.oauth2_client_secret is not None: config.oauth2_client_secret = encrypt(body.oauth2_client_secret)
    db.commit()
    db.refresh(config)
    _reschedule()
    return config


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_imap_config(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    config = _get_or_404(client.id, db)
    db.delete(config)
    db.commit()
    _reschedule()


@router.post("/test", response_model=PollResult)
def test_imap_connection(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    from ingestion.imap_fetcher import test_connection
    config = _get_or_404(client.id, db)
    ok, message = test_connection(config)
    return PollResult(status="ok" if ok else "error", messages_scanned=0, reports_ingested=0, message=message)


@router.post("/poll", response_model=PollResult)
def trigger_poll(
    slug: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_client_admin),
    client: Client = Depends(get_accessible_client),
):
    from ingestion.imap_fetcher import poll_client_imap
    config = _get_or_404(client.id, db)
    try:
        result = poll_client_imap(config, client.slug, client.id, db)
        config.last_poll_status = "ok"
        config.last_poll_message = f"Scanned {result.messages_scanned} message(s), ingested {result.reports_ingested} report(s)"
        config.last_polled_at = datetime.now(timezone.utc)
        db.commit()
        return PollResult(status="ok", messages_scanned=result.messages_scanned,
                         reports_ingested=result.reports_ingested, message=config.last_poll_message)
    except Exception as exc:
        log.error("[%s] IMAP poll error: %s", client.slug, exc, exc_info=True)
        config.last_poll_status = "error"
        config.last_poll_message = str(exc)[:512]
        config.last_polled_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="IMAP poll failed — check server logs for details")


def _reschedule():
    try:
        import api.main as app_module
        from ingestion.scheduler import sync_imap_jobs
        if hasattr(app_module, "_scheduler") and app_module._scheduler:
            sync_imap_jobs(app_module._scheduler)
    except Exception:
        pass