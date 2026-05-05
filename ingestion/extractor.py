import gzip
import hashlib
import logging
import posixpath
import zipfile
from pathlib import Path

log = logging.getLogger(__name__)

MAX_XML_BYTES = 50 * 1024 * 1024       # 50 MB decompressed limit
MAX_COMPRESS_RATIO = 100               # reject if uncompressed > 100× compressed size
_READ_CHUNK = 65536


def compute_checksum(path: Path) -> str:
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(_READ_CHUNK), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_xml(path: Path) -> str:
    """Return the raw XML string from a .xml.gz or .zip DMARC report file.

    Raises ValueError for any file that fails security checks (size, path
    traversal, compression ratio). All rejections are logged at WARNING with
    enough context to reconstruct what was attempted.
    """
    suffix = path.suffix.lower()
    compressed_size = path.stat().st_size

    if suffix == ".gz":
        return _extract_gz(path, compressed_size)

    if suffix == ".zip":
        return _extract_zip(path, compressed_size)

    raise ValueError(f"Unsupported file format: {path.suffix} ({path.name})")


def _extract_gz(path: Path, compressed_size: int) -> str:
    chunks: list[bytes] = []
    total = 0
    with gzip.open(path, "rb") as f:
        while True:
            chunk = f.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_XML_BYTES:
                log.warning(
                    "[SECURITY] GZ decompressed size exceeded %d MB limit — rejecting %s "
                    "(compressed_size=%d bytes)",
                    MAX_XML_BYTES // (1024 * 1024), path.name, compressed_size,
                )
                raise ValueError(
                    f"Decompressed XML exceeds {MAX_XML_BYTES // (1024 * 1024)} MB limit: {path.name}"
                )
            chunks.append(chunk)

    decompressed_size = total
    if compressed_size > 0:
        ratio = decompressed_size / compressed_size
        if ratio > MAX_COMPRESS_RATIO:
            log.warning(
                "[SECURITY] GZ compression ratio %.0f:1 exceeds limit of %d:1 — rejecting %s "
                "(compressed=%d bytes, decompressed=%d bytes)",
                ratio, MAX_COMPRESS_RATIO, path.name, compressed_size, decompressed_size,
            )
            raise ValueError(
                f"Suspicious compression ratio {ratio:.0f}:1 in {path.name} "
                f"(limit {MAX_COMPRESS_RATIO}:1)"
            )

    raw = b"".join(chunks)
    return _decode_xml(raw, path.name)


def _extract_zip(path: Path, compressed_size: int) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        all_names = zf.namelist()

        # Path traversal check across all entries before touching any content
        for name in all_names:
            safe = posixpath.normpath(name)
            if safe.startswith("..") or safe.startswith("/"):
                log.warning(
                    "[SECURITY] ZIP path traversal attempt in %s — entry %r",
                    path.name, name,
                )
                raise ValueError(f"Suspicious path in ZIP entry: {name!r}")

        xml_names = [n for n in all_names if n.lower().endswith(".xml")]
        if not xml_names:
            raise ValueError(f"No XML file found inside {path.name}")

        if len(xml_names) > 1:
            log.warning(
                "[SECURITY] ZIP %s contains %d XML entries — processing first (%s), ignoring: %s",
                path.name, len(xml_names), xml_names[0],
                ", ".join(xml_names[1:]),
            )

        entry_name = xml_names[0]
        info = zf.getinfo(entry_name)

        # Stream-count actual decompressed bytes — do NOT trust info.file_size,
        # which a crafted ZIP can set to 0 to bypass a header-only check.
        chunks: list[bytes] = []
        total = 0
        with zf.open(entry_name) as f:
            while True:
                chunk = f.read(_READ_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_XML_BYTES:
                    log.warning(
                        "[SECURITY] ZIP entry decompressed size exceeded %d MB limit — "
                        "rejecting %s / %s (header file_size=%d, compressed_size=%d bytes)",
                        MAX_XML_BYTES // (1024 * 1024), path.name, entry_name,
                        info.file_size, compressed_size,
                    )
                    raise ValueError(
                        f"ZIP XML entry exceeds {MAX_XML_BYTES // (1024 * 1024)} MB limit: {path.name}"
                    )
                chunks.append(chunk)

        decompressed_size = total
        entry_compressed = info.compress_size or compressed_size
        if entry_compressed > 0:
            ratio = decompressed_size / entry_compressed
            if ratio > MAX_COMPRESS_RATIO:
                log.warning(
                    "[SECURITY] ZIP compression ratio %.0f:1 exceeds limit of %d:1 — "
                    "rejecting %s / %s (entry_compressed=%d, decompressed=%d bytes)",
                    ratio, MAX_COMPRESS_RATIO, path.name, entry_name,
                    entry_compressed, decompressed_size,
                )
                raise ValueError(
                    f"Suspicious compression ratio {ratio:.0f}:1 in {path.name}/{entry_name} "
                    f"(limit {MAX_COMPRESS_RATIO}:1)"
                )

        raw = b"".join(chunks)
        return _decode_xml(raw, path.name)


def _decode_xml(raw: bytes, filename: str) -> str:
    """Decode bytes to str, logging a warning if content is not valid UTF-8."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        log.warning(
            "[SECURITY] %s contains invalid UTF-8 at byte offset %d — "
            "attempting latin-1 fallback (may indicate file corruption or encoding attack)",
            filename, exc.start,
        )
        # latin-1 decodes every byte without error; defusedxml will still reject
        # structurally invalid XML downstream.
        text = raw.decode("latin-1", errors="replace")
    _sniff_xml(text, filename)
    return text


def _sniff_xml(text: str, filename: str) -> None:
    """Raise ValueError if the decoded content does not appear to be XML.

    Strips leading BOM and whitespace, then checks the content opens with '<'.
    Catches binary payloads, plaintext, and other non-XML content before it
    reaches the XML parser. Any content starting with '<' that is not valid
    XML will still be rejected by defusedxml downstream.
    """
    head = text.lstrip("﻿ \t\n\r")
    if not head.startswith("<"):
        # Log the first 64 bytes as hex so operators can inspect without
        # storing raw potentially-malicious content in plain text logs.
        preview = raw_hex = head[:64].encode("utf-8", errors="replace").hex()
        log.warning(
            "[SECURITY] %s decompressed content does not begin with '<' — "
            "not valid XML. First 64 bytes (hex): %s",
            filename, preview,
        )
        raise ValueError(f"Decompressed content is not XML: {filename}")