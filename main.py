"""
Entry point — starts the file watcher and archive scheduler together.
Run with:  python main.py
"""
import logging
from core.logging import configure_logging
from core.database import init_db
from ingestion.scheduler import start_scheduler
from ingestion.watcher import start_watcher

configure_logging()

log = logging.getLogger(__name__)

if __name__ == "__main__":
    log.info("DMARC ingestion service starting")
    init_db()
    scheduler = start_scheduler()
    try:
        start_watcher()
    finally:
        scheduler.shutdown()
        log.info("Shutdown complete")