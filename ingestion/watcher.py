import logging
import time
from pathlib import Path
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer
from core.config import settings
from core.database import SessionLocal
from ingestion.pipeline import process_file, SUPPORTED_EXTENSIONS
from ingestion.archiver import archive_file, purge_expired_archives

log = logging.getLogger(__name__)


class ReportHandler(FileSystemEventHandler):
    def __init__(self, client_slug: str):
        self.client_slug = client_slug

    def on_created(self, event: FileCreatedEvent):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return

        log.info("[%s] Detected new file: %s", self.client_slug, path.name,
                 extra={"client": self.client_slug, "report_file": path.name})
        db = SessionLocal()
        try:
            processed = process_file(path, self.client_slug, db)
            if processed:
                archive_file(path, self.client_slug, db)
        finally:
            db.close()


def start_watcher(poll_interval: int = 2) -> None:
    incoming_root = settings.incoming_dir
    incoming_root.mkdir(parents=True, exist_ok=True)

    observer = Observer()
    watched: set[str] = set()

    for client_dir in incoming_root.iterdir():
        if client_dir.is_dir():
            _watch_client(observer, client_dir.name, watched)

    observer.start()
    log.info("File watcher started. Monitoring %s", incoming_root,
             extra={"watch_root": str(incoming_root)})

    try:
        while True:
            for client_dir in incoming_root.iterdir():
                if client_dir.is_dir() and client_dir.name not in watched:
                    _watch_client(observer, client_dir.name, watched)
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()


def _watch_client(observer: Observer, client_slug: str, watched: set[str]):
    path = settings.client_incoming_dir(client_slug)
    path.mkdir(parents=True, exist_ok=True)
    observer.schedule(ReportHandler(client_slug), str(path), recursive=False)
    watched.add(client_slug)
    log.info("Watching %s for client '%s'", path, client_slug,
             extra={"client": client_slug, "watch_path": str(path)})