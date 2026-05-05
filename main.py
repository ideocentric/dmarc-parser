"""
Entry point — starts the file watcher and archive scheduler together.
Run with:  python main.py
"""
import logging
import sys
from core.config import settings
from core.database import init_db
from ingestion.scheduler import start_scheduler
from ingestion.watcher import start_watcher

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

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