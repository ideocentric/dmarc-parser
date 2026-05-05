"""
Security-focused tests for the DMARC ingestion pipeline.

Covers: extractor (size limits, ZIP bomb, path traversal, encoding, XML sniff),
        parser (record count, count bounds, timestamp validation, IP format),
        imap_fetcher (attachment size/count limits, type rejection, decode errors),
        scanner integration (ClamAV call points in pipeline and imap_fetcher).
"""
import gzip
import io
import struct
import tempfile
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.extractor import (
    MAX_COMPRESS_RATIO,
    MAX_XML_BYTES,
    extract_xml,
)
from ingestion.parser import (
    MAX_COUNT_PER_RECORD,
    MAX_RECORDS,
    parse_dmarc_xml,
)
from ingestion.imap_fetcher import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_EMAIL,
    _extract_attachments,
    _is_dmarc_attachment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_dmarc_xml(
    record_count: int = 1,
    source_ip: str = "40.92.25.154",
    count: int = 1,
    begin_ts: str = "1746057600",
    end_ts: str = "1746143999",
) -> str:
    records = ""
    for _ in range(record_count):
        records += f"""
  <record>
    <row>
      <source_ip>{source_ip}</source_ip>
      <count>{count}</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>pass</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <result>pass</result>
      </dkim>
    </auth_results>
  </record>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <report_metadata>
    <org_name>Test Reporter</org_name>
    <email>dmarc@reporter.example</email>
    <report_id>test-001</report_id>
    <date_range>
      <begin>{begin_ts}</begin>
      <end>{end_ts}</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <adkim>r</adkim>
    <aspf>r</aspf>
    <p>none</p>
    <sp>none</sp>
    <pct>100</pct>
  </policy_published>
{records}
</feedback>"""


def _make_gz(content: bytes, tmp_path: Path, name: str = "report.xml.gz") -> Path:
    dest = tmp_path / name
    with gzip.open(dest, "wb") as f:
        f.write(content)
    return dest


def _make_zip(content: bytes, tmp_path: Path, name: str = "report.zip",
              inner_name: str = "report.xml") -> Path:
    dest = tmp_path / name
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, content)
    return dest


def _make_multipart_email(attachments: list[tuple[str, bytes, str]]) -> bytes:
    """Build a raw MIME email with the given (filename, data, content_type) attachments."""
    msg = MIMEMultipart()
    msg["Subject"] = "DMARC Report"
    msg["From"] = "reporter@example.com"
    msg["To"] = "dmarc@acme.com"
    msg.attach(MIMEText("DMARC aggregate report attached.", "plain"))
    for filename, data, ctype in attachments:
        maintype, subtype = ctype.split("/", 1)
        part = MIMEApplication(data, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
    return msg.as_bytes()


# ---------------------------------------------------------------------------
# extractor — GZ size limit
# ---------------------------------------------------------------------------

class TestExtractorGzSizeLimit:
    def test_gz_within_limit_accepted(self, tmp_path):
        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        result = extract_xml(path)
        assert "<feedback>" in result

    def test_gz_over_limit_rejected(self, tmp_path):
        oversized = b"x" * (MAX_XML_BYTES + 1)
        path = _make_gz(oversized, tmp_path)
        with pytest.raises(ValueError, match="MB limit"):
            extract_xml(path)

    def test_gz_exactly_at_limit_accepted(self, tmp_path):
        at_limit = b"<" + b"x" * (MAX_XML_BYTES - 2) + b">"
        path = _make_gz(at_limit, tmp_path)
        # Will be accepted by extractor (XML parse will fail, but no size error)
        with pytest.raises(Exception) as exc_info:
            extract_xml(path)
        assert "MB limit" not in str(exc_info.value)


# ---------------------------------------------------------------------------
# extractor — GZ compression ratio
# ---------------------------------------------------------------------------

class TestExtractorGzCompressionRatio:
    def test_high_ratio_rejected(self, tmp_path, caplog):
        # Highly compressible content — ratio will far exceed MAX_COMPRESS_RATIO
        # Use a small enough payload to stay under MAX_XML_BYTES
        compressible = (b"A" * 1000) * 200   # 200 KB of repeated bytes
        path = _make_gz(compressible, tmp_path)
        with pytest.raises(ValueError, match="compression ratio"):
            extract_xml(path)
        assert "[SECURITY]" in caplog.text

    def test_normal_ratio_accepted(self, tmp_path):
        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        result = extract_xml(path)
        assert result  # no ratio error for realistic XML


# ---------------------------------------------------------------------------
# extractor — ZIP path traversal
# ---------------------------------------------------------------------------

class TestExtractorZipPathTraversal:
    def test_path_traversal_rejected(self, tmp_path, caplog):
        dest = tmp_path / "traversal.zip"
        with zipfile.ZipFile(dest, "w") as zf:
            info = zipfile.ZipInfo("../../etc/passwd.xml")
            zf.writestr(info, b"<evil/>")
        with pytest.raises(ValueError, match="Suspicious path"):
            extract_xml(dest)
        assert "[SECURITY]" in caplog.text

    def test_absolute_path_rejected(self, tmp_path, caplog):
        dest = tmp_path / "absolute.zip"
        with zipfile.ZipFile(dest, "w") as zf:
            info = zipfile.ZipInfo("/etc/passwd.xml")
            zf.writestr(info, b"<evil/>")
        with pytest.raises(ValueError, match="Suspicious path"):
            extract_xml(dest)
        assert "[SECURITY]" in caplog.text

    def test_safe_path_accepted(self, tmp_path):
        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_zip(xml, tmp_path)
        result = extract_xml(path)
        assert "<feedback>" in result


# ---------------------------------------------------------------------------
# extractor — ZIP size limit (including spoofed file_size header)
# ---------------------------------------------------------------------------

class TestExtractorZipSizeLimit:
    def test_zip_over_limit_rejected(self, tmp_path, caplog):
        oversized = b"x" * (MAX_XML_BYTES + 1)
        path = _make_zip(oversized, tmp_path)
        with pytest.raises(ValueError, match="MB limit"):
            extract_xml(path)
        assert "[SECURITY]" in caplog.text

    def test_zip_stored_oversized_still_rejected(self, tmp_path, caplog):
        """Streaming size check catches oversized ZIP_STORED entries (no compression,
        so file_size == compress_size, but we must not rely solely on the header value)."""
        oversized = b"x" * (MAX_XML_BYTES + 1)
        dest = tmp_path / "stored.zip"
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("report.xml", oversized)
        with pytest.raises(ValueError, match="MB limit"):
            extract_xml(dest)
        assert "[SECURITY]" in caplog.text


# ---------------------------------------------------------------------------
# extractor — multiple XML entries in ZIP
# ---------------------------------------------------------------------------

class TestExtractorZipMultipleXml:
    def test_multiple_xml_warns_processes_first(self, tmp_path, caplog):
        dest = tmp_path / "multi.zip"
        xml = _minimal_dmarc_xml().encode("utf-8")
        with zipfile.ZipFile(dest, "w") as zf:
            zf.writestr("first.xml", xml)
            zf.writestr("second.xml", b"<other/>")
        result = extract_xml(dest)
        assert "<feedback>" in result
        assert "[SECURITY]" in caplog.text
        assert "second.xml" in caplog.text


# ---------------------------------------------------------------------------
# extractor — encoding fallback
# ---------------------------------------------------------------------------

class TestExtractorEncoding:
    def test_invalid_utf8_warns_and_falls_back(self, tmp_path, caplog):
        # Embed a byte that is invalid UTF-8 in an otherwise valid XML structure
        bad_bytes = b"<?xml version='1.0'?><feedback>\xff</feedback>"
        path = _make_gz(bad_bytes, tmp_path)
        result = extract_xml(path)
        assert result  # fallback succeeded
        assert "[SECURITY]" in caplog.text
        assert "UTF-8" in caplog.text

    def test_valid_utf8_no_warning(self, tmp_path, caplog):
        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        extract_xml(path)
        assert "UTF-8" not in caplog.text


# ---------------------------------------------------------------------------
# parser — record count limit
# ---------------------------------------------------------------------------

class TestParserRecordLimit:
    def test_within_limit_accepted(self):
        xml = _minimal_dmarc_xml(record_count=100)
        data = parse_dmarc_xml(xml)
        assert len(data.records) == 100

    def test_at_limit_accepted(self):
        xml = _minimal_dmarc_xml(record_count=MAX_RECORDS)
        data = parse_dmarc_xml(xml)
        assert len(data.records) == MAX_RECORDS

    def test_over_limit_rejected(self):
        xml = _minimal_dmarc_xml(record_count=MAX_RECORDS + 1)
        with pytest.raises(ValueError, match="records"):
            parse_dmarc_xml(xml)


# ---------------------------------------------------------------------------
# parser — count field bounds
# ---------------------------------------------------------------------------

class TestParserCountBounds:
    def test_normal_count_accepted(self):
        xml = _minimal_dmarc_xml(count=500)
        data = parse_dmarc_xml(xml)
        assert data.records[0].count == 500

    def test_huge_count_clamped_with_warning(self, caplog):
        xml = _minimal_dmarc_xml(count=MAX_COUNT_PER_RECORD + 1)
        data = parse_dmarc_xml(xml)
        assert data.records[0].count == MAX_COUNT_PER_RECORD
        assert "[SECURITY]" in caplog.text

    def test_negative_count_defaults_to_one(self, caplog):
        xml = _minimal_dmarc_xml(count=-5)
        data = parse_dmarc_xml(xml)
        assert data.records[0].count == 1
        assert "[SECURITY]" in caplog.text

    def test_non_integer_count_defaults_to_one(self, caplog):
        xml = _minimal_dmarc_xml(count="abc")
        data = parse_dmarc_xml(xml)
        assert data.records[0].count == 1
        assert "[SECURITY]" in caplog.text


# ---------------------------------------------------------------------------
# parser — timestamp validation
# ---------------------------------------------------------------------------

class TestParserTimestamps:
    def test_valid_timestamps_parsed(self):
        xml = _minimal_dmarc_xml(begin_ts="1746057600", end_ts="1746143999")
        data = parse_dmarc_xml(xml)
        assert data.begin_date.year == 2025

    def test_out_of_range_timestamp_uses_now(self, caplog):
        xml = _minimal_dmarc_xml(begin_ts="99999999999")
        data = parse_dmarc_xml(xml)
        from datetime import datetime, timezone
        # Should not be the year 5138 — should fall back to now
        assert data.begin_date.year >= 2025
        assert "[SECURITY]" in caplog.text

    def test_negative_timestamp_uses_now(self, caplog):
        xml = _minimal_dmarc_xml(begin_ts="-1")
        data = parse_dmarc_xml(xml)
        assert "[SECURITY]" in caplog.text

    def test_non_integer_timestamp_uses_now(self, caplog):
        xml = _minimal_dmarc_xml(begin_ts="not-a-timestamp")
        data = parse_dmarc_xml(xml)
        assert "[SECURITY]" in caplog.text


# ---------------------------------------------------------------------------
# parser — source_ip validation
# ---------------------------------------------------------------------------

class TestParserSourceIp:
    def test_valid_ipv4_no_warning(self, caplog):
        xml = _minimal_dmarc_xml(source_ip="192.0.2.1")
        parse_dmarc_xml(xml)
        assert "source_ip" not in caplog.text

    def test_valid_ipv6_no_warning(self, caplog):
        xml = _minimal_dmarc_xml(source_ip="2001:db8::1")
        parse_dmarc_xml(xml)
        assert "source_ip" not in caplog.text

    def test_suspicious_ip_warns(self, caplog):
        # Use a string that is valid XML text but not a valid IP format
        xml = _minimal_dmarc_xml(source_ip="not-an-ip-address")
        data = parse_dmarc_xml(xml)
        assert "[SECURITY]" in caplog.text
        assert data.records[0].source_ip == "not-an-ip-address"  # stored, not dropped


# ---------------------------------------------------------------------------
# parser — malformed XML
# ---------------------------------------------------------------------------

class TestParserMalformedXml:
    def test_not_well_formed_raises(self):
        with pytest.raises(Exception):
            parse_dmarc_xml("<feedback><unclosed>")

    def test_xxe_attempt_blocked(self):
        xxe = """<?xml version="1.0"?>
<!DOCTYPE feedback [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<feedback>&xxe;</feedback>"""
        with pytest.raises(Exception):
            parse_dmarc_xml(xxe)

    def test_billion_laughs_blocked(self):
        billion = """<?xml version="1.0"?>
<!DOCTYPE lolz [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<feedback>&lol3;</feedback>"""
        with pytest.raises(Exception):
            parse_dmarc_xml(billion)


# ---------------------------------------------------------------------------
# imap_fetcher — attachment acceptance/rejection
# ---------------------------------------------------------------------------

class TestImapAttachmentFiltering:
    def _make_raw(self, attachments):
        return _make_multipart_email(attachments)

    def test_valid_gz_attachment_accepted(self):
        xml = _minimal_dmarc_xml().encode("utf-8")
        gz = io.BytesIO()
        with gzip.GzipFile(fileobj=gz, mode="wb") as f:
            f.write(xml)
        raw = self._make_raw([("report.xml.gz", gz.getvalue(), "application/gzip")])
        result = _extract_attachments(raw, "acme-test", 1)
        assert len(result) == 1
        assert result[0][0] == "report.xml.gz"

    def test_wrong_extension_rejected(self, caplog):
        raw = self._make_raw([("report.pdf", b"%PDF-1.4", "application/pdf")])
        result = _extract_attachments(raw, "acme-test", 1)
        assert result == []

    def test_wrong_mime_type_rejected(self, caplog):
        raw = self._make_raw([("report.xml.gz", b"data", "text/plain")])
        result = _extract_attachments(raw, "acme-test", 1)
        assert result == []

    def test_no_attachments_returns_empty(self):
        msg = MIMEMultipart()
        msg.attach(MIMEText("No attachments here."))
        result = _extract_attachments(msg.as_bytes(), "acme-test", 1)
        assert result == []


# ---------------------------------------------------------------------------
# imap_fetcher — attachment size limit
# ---------------------------------------------------------------------------

class TestImapAttachmentSizeLimit:
    def test_oversized_attachment_rejected(self, caplog):
        oversized = b"x" * (MAX_ATTACHMENT_BYTES + 1)
        raw = _make_multipart_email([("report.xml.gz", oversized, "application/gzip")])
        result = _extract_attachments(raw, "acme-test", 42)
        assert result == []
        assert "[SECURITY]" in caplog.text
        assert "exceeds" in caplog.text

    def test_at_limit_accepted(self):
        at_limit = b"x" * MAX_ATTACHMENT_BYTES
        raw = _make_multipart_email([("report.xml.gz", at_limit, "application/gzip")])
        result = _extract_attachments(raw, "acme-test", 42)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# imap_fetcher — attachment count limit
# ---------------------------------------------------------------------------

class TestImapAttachmentCountLimit:
    def test_count_limit_enforced(self, caplog):
        xml = _minimal_dmarc_xml().encode("utf-8")
        gz = io.BytesIO()
        with gzip.GzipFile(fileobj=gz, mode="wb") as f:
            f.write(xml)
        gz_bytes = gz.getvalue()

        attachments = [
            (f"report_{i}.xml.gz", gz_bytes, "application/gzip")
            for i in range(MAX_ATTACHMENTS_PER_EMAIL + 5)
        ]
        raw = _make_multipart_email(attachments)
        result = _extract_attachments(raw, "acme-test", 99)
        assert len(result) == MAX_ATTACHMENTS_PER_EMAIL
        assert "[SECURITY]" in caplog.text
        assert "limit" in caplog.text

# ---------------------------------------------------------------------------
# extractor — XML sniff
# ---------------------------------------------------------------------------

class TestExtractorXmlSniff:
    def test_binary_payload_in_gz_rejected(self, tmp_path, caplog):
        # PE executable magic bytes — definitely not XML
        binary = b"\x4d\x5a\x90\x00" + b"\x00" * 100
        path = _make_gz(binary, tmp_path, "malware.xml.gz")
        with pytest.raises(ValueError, match="not XML"):
            extract_xml(path)
        assert "[SECURITY]" in caplog.text

    def test_plaintext_in_gz_rejected(self, tmp_path, caplog):
        path = _make_gz(b"this is a plain text file, not XML", tmp_path)
        with pytest.raises(ValueError, match="not XML"):
            extract_xml(path)
        assert "[SECURITY]" in caplog.text

    def test_valid_xml_passes_sniff(self, tmp_path):
        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        result = extract_xml(path)
        assert "<feedback>" in result

    def test_xml_with_leading_whitespace_passes(self, tmp_path):
        xml = b"\n\n  " + _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        result = extract_xml(path)
        assert "<feedback>" in result

    def test_xml_with_bom_passes(self, tmp_path):
        # UTF-8 BOM followed by valid XML
        xml = b"\xef\xbb\xbf" + _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path)
        result = extract_xml(path)
        assert "<feedback>" in result


# ---------------------------------------------------------------------------
# ClamAV integration — scan_bytes called at the right points
# ---------------------------------------------------------------------------

class TestScannerIntegration:
    def test_pipeline_calls_scan_bytes(self, tmp_path, monkeypatch):
        """scan_bytes is called in pipeline.process_file before extract_xml."""
        from ingestion import pipeline as pipeline_mod

        scan_calls = []

        def fake_scan(data: bytes, filename: str) -> None:
            scan_calls.append(filename)

        monkeypatch.setattr(pipeline_mod, "scan_bytes", fake_scan)

        xml = _minimal_dmarc_xml().encode("utf-8")
        path = _make_gz(xml, tmp_path, "report.xml.gz")

        # process_file needs a DB session and client — mock at the DB layer
        from unittest.mock import MagicMock
        from core.models import Client, Domain
        fake_client = MagicMock(spec=Client)
        fake_client.id = 1

        fake_db = MagicMock()
        fake_db.query.return_value.filter_by.return_value.first.side_effect = [
            fake_client,   # Client lookup
            None,          # Domain lookup
        ]

        with patch.object(pipeline_mod, "write_report", return_value=None), \
             patch.object(pipeline_mod, "run_intelligence"):
            pipeline_mod.process_file(path, "acme-test", fake_db)

        assert len(scan_calls) == 1
        assert scan_calls[0] == "report.xml.gz"

    def test_imap_fetcher_calls_scan_bytes_per_attachment(self, monkeypatch):
        """scan_bytes is called in _extract_attachments for each accepted attachment."""
        from ingestion import imap_fetcher as fetcher_mod

        scan_calls = []

        def fake_scan(data: bytes, filename: str) -> None:
            scan_calls.append(filename)

        monkeypatch.setattr(fetcher_mod, "scan_bytes", fake_scan)

        xml = _minimal_dmarc_xml().encode("utf-8")
        gz = io.BytesIO()
        with gzip.GzipFile(fileobj=gz, mode="wb") as f:
            f.write(xml)
        gz_bytes = gz.getvalue()

        raw = _make_multipart_email([
            ("report1.xml.gz", gz_bytes, "application/gzip"),
            ("report2.xml.gz", gz_bytes, "application/gzip"),
        ])
        result = fetcher_mod._extract_attachments(raw, "acme-test", 1)

        assert len(result) == 2
        assert len(scan_calls) == 2
        assert "report1.xml.gz" in scan_calls
        assert "report2.xml.gz" in scan_calls

    def test_imap_fetcher_drops_attachment_when_scan_raises(self, monkeypatch, caplog):
        """An attachment is dropped (not raised) when scan_bytes raises ValueError."""
        from ingestion import imap_fetcher as fetcher_mod

        def fake_scan(data: bytes, filename: str) -> None:
            raise ValueError("Malware detected")

        monkeypatch.setattr(fetcher_mod, "scan_bytes", fake_scan)

        xml = _minimal_dmarc_xml().encode("utf-8")
        gz = io.BytesIO()
        with gzip.GzipFile(fileobj=gz, mode="wb") as f:
            f.write(xml)

        raw = _make_multipart_email([("report.xml.gz", gz.getvalue(), "application/gzip")])
        result = fetcher_mod._extract_attachments(raw, "acme-test", 1)

        assert result == []
        assert "[SECURITY]" in caplog.text
        assert "rejected by scanner" in caplog.text
