"""
Centralised logging configuration.

Call configure_logging() once at application startup (main.py / api/main.py lifespan).
All subsequent getLogger() calls inherit the configured handlers and formatter.

Format selection:
  LOG_FORMAT=json  — one JSON object per line; for Graylog / ELK / Loki shippers.
  LOG_FORMAT=text  — human-readable; default for local development.
  app_env != "development" automatically activates JSON format even if LOG_FORMAT is
  not explicitly set, so production deployments get structured logs without extra config.

Structured extra fields (available in JSON output):
  client      — client slug for ingestion / pipeline operations
  filename    — report filename being processed
  file_size   — compressed file size in bytes
  org         — reporting organisation from the DMARC report
  policy_domain — domain the DMARC policy covers
  records     — number of records in the parsed report
  records_updated — count of records enriched (geo / WHOIS)
  ips_queried — unique IPs looked up in a WHOIS enrichment pass
"""
import logging
import sys
from core.config import settings


class _ContextFilter(logging.Filter):
    """Injects environment and service name into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.environment = settings.app_env
        record.service = "dmarc"
        return True


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    use_json = settings.log_format == "json" or settings.app_env != "development"

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())

    if use_json:
        from pythonjsonlogger.json import JsonFormatter
        handler.setFormatter(
            JsonFormatter(
                fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%SZ",
                rename_fields={
                    "asctime":   "timestamp",
                    "levelname": "level",
                    "name":      "logger",
                },
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]

    # Suppress noisy third-party loggers that add no diagnostic value.
    for noisy in ("watchdog", "apscheduler", "uvicorn.access",
                  "multipart", "imapclient"):
        logging.getLogger(noisy).setLevel(logging.WARNING)