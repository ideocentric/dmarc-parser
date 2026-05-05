"""
Tests for IMAP email parsing — no real IMAP server required.
"""
import gzip
import io
import zipfile
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ingestion.imap_fetcher import _extract_attachments, _is_dmarc_attachment

SAMPLE_XML = b"""<?xml version="1.0"?>
<feedback><report_metadata><org_name>Test</org_name></report_metadata></feedback>"""


def _make_email(attachments: list[tuple[str, bytes, str]]) -> bytes:
    """Build a raw MIME email with the given (filename, data, content_type) attachments."""
    msg = MIMEMultipart()
    msg["From"] = "dmarc@google.com"
    msg["To"] = "reports@example.com"
    msg["Subject"] = "Report Domain: example.com"
    msg.attach(MIMEText("DMARC aggregate report attached.", "plain"))
    for filename, data, content_type in attachments:
        part = MIMEApplication(data, Name=filename)
        part["Content-Disposition"] = f'attachment; filename="{filename}"'
        part.set_type(content_type)
        msg.attach(part)
    return msg.as_bytes()


def _gz_payload() -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(SAMPLE_XML)
    return buf.getvalue()


def _zip_payload(inner_filename: str = "report.xml") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_filename, SAMPLE_XML)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# _is_dmarc_attachment
# ---------------------------------------------------------------------------

def test_gz_attachment_detected():
    from email.message import Message
    part = Message()
    part["Content-Type"] = "application/gzip"
    part["Content-Disposition"] = 'attachment; filename="report.xml.gz"'
    assert _is_dmarc_attachment(part)


def test_zip_attachment_detected():
    from email.message import Message
    part = Message()
    part["Content-Type"] = "application/zip"
    part["Content-Disposition"] = 'attachment; filename="report.zip"'
    assert _is_dmarc_attachment(part)


def test_non_dmarc_attachment_ignored():
    from email.message import Message
    part = Message()
    part["Content-Type"] = "image/png"
    part["Content-Disposition"] = 'attachment; filename="logo.png"'
    assert not _is_dmarc_attachment(part)


# ---------------------------------------------------------------------------
# _extract_attachments
# ---------------------------------------------------------------------------

def test_extract_gz_attachment():
    raw = _make_email([("example.com!report.xml.gz", _gz_payload(), "application/gzip")])
    attachments = _extract_attachments(raw, "test-client", 0)
    assert len(attachments) == 1
    filename, data = attachments[0]
    assert filename.endswith(".gz")
    assert data == _gz_payload()


def test_extract_zip_attachment():
    raw = _make_email([("example.com!report.zip", _zip_payload(), "application/zip")])
    attachments = _extract_attachments(raw, "test-client", 0)
    assert len(attachments) == 1
    filename, data = attachments[0]
    assert filename.endswith(".zip")


def test_extract_multiple_attachments():
    raw = _make_email([
        ("report1.xml.gz", _gz_payload(), "application/gzip"),
        ("report2.zip", _zip_payload(), "application/zip"),
    ])
    attachments = _extract_attachments(raw, "test-client", 0)
    assert len(attachments) == 2


def test_no_dmarc_attachments_returns_empty():
    msg = MIMEMultipart()
    msg["From"] = "someone@example.com"
    msg["Subject"] = "Hello"
    msg.attach(MIMEText("Just a regular email", "plain"))
    attachments = _extract_attachments(msg.as_bytes(), "test-client", 0)
    assert attachments == []


def test_email_with_text_only():
    raw = MIMEText("No attachments here").as_bytes()
    assert _extract_attachments(raw, "test-client", 0) == []


# ---------------------------------------------------------------------------
# crypto round-trip (requires no ENCRYPTION_KEY — plain-text fallback)
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip():
    from core.crypto import encrypt, decrypt
    secret = "hunter2"
    assert decrypt(encrypt(secret)) == secret