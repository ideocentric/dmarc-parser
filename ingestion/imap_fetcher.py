import email
import email.policy
import logging
import tempfile
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from typing import NamedTuple

from sqlalchemy.orm import Session
from core.crypto import decrypt
from core.models import ImapConfig
from ingestion.scanner import scan_bytes

log = logging.getLogger(__name__)
DMARC_EXTENSIONS = {".gz", ".zip", ".xml"}
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024   # 25 MB per attachment (pre-decompression)
MAX_ATTACHMENTS_PER_EMAIL = 20            # ignore further attachments beyond this


class FetchResult(NamedTuple):
    messages_scanned: int
    reports_ingested: int


def _is_dmarc_attachment(part: Message) -> bool:
    filename = part.get_filename() or ""
    suffix = Path(filename).suffix.lower()
    content_type = part.get_content_type()
    dmarc_types = {
        "application/zip", "application/gzip", "application/x-gzip",
        "application/octet-stream", "application/x-zip-compressed",
        "text/xml", "application/xml",
    }
    return suffix in DMARC_EXTENSIONS and content_type in dmarc_types


def _extract_attachments(raw_message: bytes, client_slug: str, uid) -> list[tuple[str, bytes]]:
    msg = email.message_from_bytes(raw_message, policy=email.policy.compat32)
    attachments = []
    attachment_count = 0

    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue

        filename = part.get_filename() or ""
        content_type = part.get_content_type()

        if not _is_dmarc_attachment(part):
            if filename:
                log.debug(
                    "[%s] uid=%s — skipping attachment %r (content-type=%s, "
                    "extension not in DMARC allowlist)",
                    client_slug, uid, filename, content_type,
                )
            continue

        if attachment_count >= MAX_ATTACHMENTS_PER_EMAIL:
            log.warning(
                "[SECURITY][%s] uid=%s — attachment limit (%d) reached, "
                "ignoring remaining attachments",
                client_slug, uid, MAX_ATTACHMENTS_PER_EMAIL,
            )
            break

        try:
            payload = part.get_payload(decode=True)
        except Exception as exc:
            log.warning(
                "[SECURITY][%s] uid=%s — failed to decode attachment %r: %s",
                client_slug, uid, filename, exc,
            )
            continue

        if not payload:
            log.warning(
                "[%s] uid=%s — attachment %r decoded to empty payload, skipping",
                client_slug, uid, filename,
            )
            continue

        payload_size = len(payload)
        if payload_size > MAX_ATTACHMENT_BYTES:
            log.warning(
                "[SECURITY][%s] uid=%s — attachment %r size %d bytes exceeds "
                "limit of %d bytes — skipping",
                client_slug, uid, filename, payload_size, MAX_ATTACHMENT_BYTES,
            )
            continue

        safe_filename = filename or f"dmarc_report{part.get_content_subtype()}"

        # ClamAV scan on raw attachment bytes before writing to a temp file.
        # scan_bytes() is a no-op when CLAMAV_ENABLED=false.
        try:
            scan_bytes(payload, safe_filename)
        except ValueError as exc:
            log.warning(
                "[SECURITY][%s] uid=%s — attachment %r rejected by scanner: %s",
                client_slug, uid, safe_filename, exc,
            )
            continue

        log.info(
            "[%s] uid=%s — accepted attachment %r (%d bytes, content-type=%s)",
            client_slug, uid, safe_filename, payload_size, content_type,
        )
        attachments.append((safe_filename, payload))
        attachment_count += 1

    return attachments


def _connect(config: ImapConfig):
    """Return an authenticated IMAPClient based on auth_type."""
    try:
        import imapclient
    except ImportError:
        raise RuntimeError("imapclient is not installed")

    server = imapclient.IMAPClient(
        host=config.host,
        port=config.port,
        use_uid=True,
        ssl=config.use_ssl,
    )

    if config.auth_type == "office365":
        from ingestion.m365_auth import get_access_token
        secret = decrypt(config.oauth2_client_secret)
        token = get_access_token(
            tenant_id=config.oauth2_tenant_id,
            client_id=config.oauth2_client_id,
            client_secret=secret,
        )
        server.oauth2_login(config.username, token)
        log.info("Authenticated to Office 365 mailbox %s via OAuth2", config.username)
    else:
        password = decrypt(config.encrypted_password)
        server.login(config.username, password)
        log.info("Authenticated to IMAP server %s as %s", config.host, config.username)

    return server


def poll_client_imap(config: ImapConfig, client_slug: str, client_id: int, db: Session) -> FetchResult:
    from ingestion.pipeline import process_file
    from ingestion.archiver import archive_file

    messages_scanned = 0
    reports_ingested = 0

    with _connect(config) as server:
        server.select_folder(config.inbox_folder, readonly=False)
        message_ids = server.search(["UNSEEN"])
        log.info("[%s] Found %d unread message(s) in %s", client_slug, len(message_ids), config.inbox_folder)

        for uid in message_ids:
            messages_scanned += 1
            try:
                fetched = server.fetch([uid], ["RFC822"])
                raw = fetched[uid][b"RFC822"]
            except Exception:
                log.exception("[%s] Failed to fetch uid=%s", client_slug, uid)
                continue

            attachments = _extract_attachments(raw, client_slug, uid)
            if not attachments:
                log.debug("[%s] uid=%s — no DMARC attachments found, marking seen", client_slug, uid)
                import imapclient
                server.set_flags([uid], [imapclient.SEEN])
                continue

            for filename, data in attachments:
                suffix = Path(filename).suffix.lower() or ".gz"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(data)
                    tmp_path = Path(tmp.name)
                try:
                    ok = process_file(tmp_path, client_slug, db)
                    if ok:
                        reports_ingested += 1
                        archive_file(tmp_path, client_slug, db)
                    else:
                        tmp_path.unlink(missing_ok=True)
                except Exception:
                    log.exception("[%s] Pipeline error for attachment %r uid=%s", client_slug, filename, uid)
                    tmp_path.unlink(missing_ok=True)

            if config.processed_folder:
                try:
                    _ensure_folder(server, config.processed_folder)
                    server.move([uid], config.processed_folder)
                    log.debug("[%s] uid=%s — moved to %s", client_slug, uid, config.processed_folder)
                except Exception:
                    import imapclient
                    log.warning("[%s] uid=%s — could not move to %s, marking seen instead",
                                client_slug, uid, config.processed_folder)
                    server.set_flags([uid], [imapclient.SEEN])
            else:
                import imapclient
                server.set_flags([uid], [imapclient.SEEN])

    log.info(
        "[%s] IMAP poll complete — scanned=%d ingested=%d",
        client_slug, messages_scanned, reports_ingested,
    )
    return FetchResult(messages_scanned=messages_scanned, reports_ingested=reports_ingested)


def _ensure_folder(server, folder_name: str) -> None:
    existing = [f[2] for f in server.list_folders()]
    if folder_name not in existing:
        server.create_folder(folder_name)


def test_connection(config: ImapConfig) -> tuple[bool, str]:
    try:
        with _connect(config) as server:
            folders = [f[2] for f in server.list_folders()]
            auth_label = "OAuth2" if config.auth_type == "office365" else "password"
            return True, f"Connected ({auth_label}). Folders: {', '.join(str(f) for f in folders[:10])}"
    except Exception as exc:
        return False, str(exc)