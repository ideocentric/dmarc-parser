import logging
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from core.config import settings
from core.database import SessionLocal
from core.models import Client, ImapConfig
from ingestion.archiver import purge_expired_archives

log = logging.getLogger(__name__)


def _run_purge():
    db = SessionLocal()
    try:
        for client in db.query(Client).filter_by(is_active=True).all():
            purge_expired_archives(client.slug, db, client.id)
    finally:
        db.close()


def _poll_single_imap(config_id: int) -> None:
    from ingestion.imap_fetcher import poll_client_imap
    db = SessionLocal()
    try:
        config = db.query(ImapConfig).filter_by(id=config_id, is_active=True).first()
        if not config:
            return
        client = db.query(Client).filter_by(id=config.client_id, is_active=True).first()
        if not client:
            return

        log.info("IMAP poll starting for client '%s'", client.slug)
        try:
            result = poll_client_imap(config, client.slug, client.id, db)
            config.last_poll_status = "ok"
            config.last_poll_message = (
                f"Scanned {result.messages_scanned} message(s), "
                f"ingested {result.reports_ingested} report(s)"
            )
            log.info("IMAP poll OK for '%s': %s", client.slug, config.last_poll_message)
        except Exception as exc:
            config.last_poll_status = "error"
            config.last_poll_message = str(exc)[:512]
            log.error("IMAP poll failed for '%s': %s", client.slug, exc)
        finally:
            config.last_polled_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


def sync_imap_jobs(scheduler: BackgroundScheduler) -> None:
    db = SessionLocal()
    try:
        configs = db.query(ImapConfig).filter_by(is_active=True).all()
        active_job_ids = set()
        for config in configs:
            job_id = f"imap_poll_{config.id}"
            active_job_ids.add(job_id)
            scheduler.add_job(
                _poll_single_imap, trigger="interval",
                minutes=config.poll_interval_minutes, args=[config.id],
                id=job_id, replace_existing=True, max_instances=1, coalesce=True,
            )
        for job in scheduler.get_jobs():
            if job.id.startswith("imap_poll_") and job.id not in active_job_ids:
                scheduler.remove_job(job.id)
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(_run_purge, trigger="cron", hour=2, minute=0,
                      id="purge_archives", replace_existing=True)
    scheduler.add_job(lambda: sync_imap_jobs(scheduler), trigger="interval",
                      minutes=5, id="sync_imap_jobs", replace_existing=True)
    scheduler.start()
    sync_imap_jobs(scheduler)
    log.info("Scheduler started")
    return scheduler