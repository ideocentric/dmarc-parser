import logging
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlalchemy.orm import Session
from core.config import settings
from core.models import ProcessedFile

log = logging.getLogger(__name__)


def archive_file(path: Path, client_slug: str, db: Session) -> Path | None:
    month_dir = settings.client_archive_dir(client_slug) / datetime.now().strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)
    dest = month_dir / path.name
    try:
        shutil.move(str(path), dest)
    except Exception as exc:
        log.error("[%s] Could not archive %s: %s", client_slug, path.name, exc)
        return None

    record = db.query(ProcessedFile).filter_by(filename=path.name).first()
    if record:
        record.archived_at = datetime.now(timezone.utc)
        db.commit()

    log.debug("[%s] Archived %s → %s", client_slug, path.name, dest)
    return dest


def purge_expired_archives(client_slug: str, db: Session, client_id: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.archive_retention_days)
    archive_root = settings.client_archive_dir(client_slug)
    removed = 0

    for file in archive_root.rglob("*"):
        if not file.is_file():
            continue
        mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            try:
                file.unlink()
                removed += 1
                record = db.query(ProcessedFile).filter_by(client_id=client_id, filename=file.name).first()
                if record:
                    record.removed_at = datetime.now(timezone.utc)
                    db.commit()
            except Exception as exc:
                log.error("[%s] Could not remove %s: %s", client_slug, file, exc)

    if removed:
        log.info("[%s] Purged %d expired archive files", client_slug, removed)
    return removed