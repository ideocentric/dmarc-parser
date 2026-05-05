"""
ClamAV antivirus scanning for ingested DMARC report files.

Disabled by default. Enable via CLAMAV_ENABLED=true in .env.
Requires a running clamd daemon and the python-clamd package.

Scan results:
  OK      — file is clean, processing continues
  FOUND   — malware detected, file is rejected with [SECURITY] ERROR log
  ERROR   — clamd reported a scan error, treated as FOUND (safe default)
  Unreachable — behaviour controlled by CLAMAV_FAIL_OPEN:
                False (default) — reject the file (fail closed, compliance-safe)
                True            — allow the file through with a WARNING log
"""
import logging
from functools import lru_cache

from core.config import settings

log = logging.getLogger(__name__)


def scan_bytes(data: bytes, filename: str) -> None:
    """Scan raw bytes with ClamAV.

    Does nothing if CLAMAV_ENABLED is False.
    Raises ValueError if the content is infected or if clamd is unreachable
    and CLAMAV_FAIL_OPEN is False.
    """
    if not settings.clamav_enabled:
        return

    clamd = _get_clamd()

    try:
        result = clamd.instream(data)
        # result is {"stream": ("OK", None)} or {"stream": ("FOUND", "Virus.Name")}
        status, virus_name = result.get("stream", ("ERROR", "no result returned"))
    except Exception as exc:
        _handle_unreachable(filename, exc)
        return

    if status == "OK":
        log.debug("[%s] ClamAV scan clean", filename)
        return

    if status == "FOUND":
        log.error(
            "[SECURITY] MALWARE DETECTED in %s — ClamAV signature: %s — file rejected",
            filename, virus_name,
        )
        raise ValueError(f"Malware detected in {filename}: {virus_name}")

    # status == "ERROR" or unexpected value — treat as infected (safe default)
    log.error(
        "[SECURITY] ClamAV returned unexpected status %r for %s — rejecting as precaution",
        status, filename,
    )
    raise ValueError(f"ClamAV scan error for {filename}: status={status!r}")


def ping() -> bool:
    """Return True if clamd is reachable. Used by health checks."""
    if not settings.clamav_enabled:
        return True
    try:
        _get_clamd().ping()
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _get_clamd():
    """Return a clamd connection, cached per process.

    The cache is invalidated implicitly on reconnect errors in scan_bytes.
    lru_cache(maxsize=1) means a single shared instance per worker process,
    which is appropriate since clamd connections are thread-safe.
    """
    try:
        import clamd as clamd_lib
    except ImportError:
        raise RuntimeError(
            "python-clamd is required when CLAMAV_ENABLED=true. "
            "Install it with: pip install python-clamd"
        )
    cd = clamd_lib.ClamdNetworkSocket(
        host=settings.clamav_host,
        port=settings.clamav_port,
        timeout=30,
    )
    log.info(
        "ClamAV scanning enabled — connecting to clamd at %s:%d (fail_open=%s)",
        settings.clamav_host, settings.clamav_port, settings.clamav_fail_open,
    )
    return cd


def _handle_unreachable(filename: str, exc: Exception) -> None:
    """Handle a clamd connection or scan error based on fail_open setting."""
    if settings.clamav_fail_open:
        log.warning(
            "[SECURITY] ClamAV unavailable for %s (%s) — "
            "CLAMAV_FAIL_OPEN=true, allowing file through. "
            "Investigate clamd connectivity.",
            filename, exc,
        )
    else:
        log.error(
            "[SECURITY] ClamAV unavailable for %s (%s) — "
            "CLAMAV_FAIL_OPEN=false, rejecting file. "
            "Set CLAMAV_FAIL_OPEN=true to allow processing when clamd is down.",
            filename, exc,
        )
        raise ValueError(
            f"ClamAV unavailable and CLAMAV_FAIL_OPEN=false — rejecting {filename}"
        )