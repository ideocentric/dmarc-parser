"""
Tests for core.logging.configure_logging().

Verifies:
  - Text mode produces human-readable output (no JSON)
  - JSON mode produces valid JSON with required fields
  - Extra fields (client, report_file, etc.) appear in JSON output
  - Reserved LogRecord attributes are not clobbered by extra keys
  - configure_logging() is idempotent (safe to call multiple times)
"""
import io
import json
import logging
import pytest
from unittest.mock import patch

from core.logging import configure_logging


def _capture(log_format: str, level: str = "INFO", extra: dict | None = None) -> str:
    """
    Run configure_logging() with the given format and return the captured log line.

    Patches core.logging.settings (the reference already imported by the module)
    and swaps the handler's stream to a StringIO buffer after setup so the output
    is captured without redirecting sys.stdout.
    """
    buf = io.StringIO()

    with patch("core.logging.settings") as mock_cfg:
        mock_cfg.log_level = level
        mock_cfg.log_format = log_format
        mock_cfg.app_env = "production" if log_format == "json" else "development"

        configure_logging()

        # Redirect the handler that configure_logging installed to our buffer.
        root = logging.getLogger()
        assert len(root.handlers) == 1, "configure_logging should leave exactly one handler"
        root.handlers[0].stream = buf

        log = logging.getLogger("test.logging")
        if extra:
            log.info("test message", extra=extra)
        else:
            log.info("test message")

    return buf.getvalue().strip()


class TestTextFormat:
    def test_produces_human_readable_output(self):
        assert "test message" in _capture("text")

    def test_is_not_json(self):
        assert not _capture("text").startswith("{")

    def test_level_appears(self):
        assert "INFO" in _capture("text")

    def test_logger_name_appears(self):
        assert "test.logging" in _capture("text")


class TestJsonFormat:
    def _parse(self, log_format: str = "json", extra: dict | None = None) -> dict:
        return json.loads(_capture(log_format, extra=extra))

    def test_output_is_valid_json(self):
        self._parse()  # raises json.JSONDecodeError if invalid

    def test_required_fields_present(self):
        record = self._parse()
        for field in ("timestamp", "level", "logger", "message"):
            assert field in record, f"missing field: {field}"

    def test_context_fields_injected(self):
        record = self._parse()
        assert record.get("environment") == "production"
        assert record.get("service") == "dmarc"

    def test_level_value(self):
        assert self._parse()["level"] == "INFO"

    def test_logger_value(self):
        assert self._parse()["logger"] == "test.logging"

    def test_message_value(self):
        assert self._parse()["message"] == "test message"

    def test_extra_client_field(self):
        record = self._parse(extra={"client": "acme-corp"})
        assert record.get("client") == "acme-corp"

    def test_extra_report_file_field(self):
        record = self._parse(extra={
            "client": "acme-corp",
            "report_file": "google.com!acme.corp!123.xml.gz",
            "file_size": 18432,
        })
        assert record.get("report_file") == "google.com!acme.corp!123.xml.gz"
        assert record.get("file_size") == 18432

    def test_extra_ingestion_fields(self):
        record = self._parse(extra={
            "client": "acme-corp",
            "org": "Google LLC",
            "policy_domain": "acme.corp",
            "records": 14,
        })
        assert record.get("org") == "Google LLC"
        assert record.get("policy_domain") == "acme.corp"
        assert record.get("records") == 14

    def test_extra_enrichment_fields(self):
        record = self._parse(extra={
            "client": "acme-corp",
            "enrichment": "geo",
            "records_updated": 12,
        })
        assert record.get("enrichment") == "geo"
        assert record.get("records_updated") == 12

    def test_report_file_does_not_clobber_builtin_filename(self):
        """report_file must not collide with LogRecord.filename (the Python source path)."""
        record = self._parse(extra={"report_file": "dmarc-report.xml.gz"})
        assert record.get("report_file") == "dmarc-report.xml.gz"
        # If python-json-logger also emits the built-in filename attribute,
        # it must refer to a .py file — not to the report filename.
        if "filename" in record:
            assert record["filename"].endswith(".py"), (
                f"LogRecord.filename was clobbered: {record['filename']}"
            )

    def test_idempotent_single_handler(self):
        """Calling configure_logging() twice must not duplicate root handlers."""
        with patch("core.logging.settings") as mock_cfg:
            mock_cfg.log_level = "INFO"
            mock_cfg.log_format = "json"
            mock_cfg.app_env = "production"

            configure_logging()
            configure_logging()

            assert len(logging.getLogger().handlers) == 1