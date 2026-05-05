import logging
from pathlib import Path
from sqlalchemy.orm import Session
from core.models import Client, Domain
from ingestion.extractor import compute_checksum, extract_xml
from ingestion.parser import parse_dmarc_xml
from ingestion.scanner import scan_bytes
from ingestion.writer import write_report
from intelligence.engine import run_intelligence

log = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".gz", ".zip"}


def process_file(path: Path, client_slug: str, db: Session) -> bool:
    """
    Full ingestion pipeline for a single report file.
    Returns True if processed, False if skipped or errored.
    """
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False

    file_size = path.stat().st_size
    log.info("[%s] Processing %s (%d bytes)", client_slug, path.name, file_size)

    try:
        checksum = compute_checksum(path)
        # ClamAV scan on raw compressed bytes before decompression.
        # scan_bytes() is a no-op when CLAMAV_ENABLED=false.
        scan_bytes(path.read_bytes(), path.name)
        xml_string = extract_xml(path)
        report_data = parse_dmarc_xml(xml_string)
    except ValueError as exc:
        # ValueError covers all deliberate security rejections:
        # extractor size/ratio/path checks, XML sniff, parser bounds, ClamAV FOUND
        log.warning(
            "[SECURITY][%s] Rejected %s (%d bytes): %s",
            client_slug, path.name, file_size, exc,
        )
        return False
    except Exception:
        log.exception(
            "[%s] Unexpected error extracting/parsing %s (%d bytes)",
            client_slug, path.name, file_size,
        )
        return False

    log.info(
        "[%s] Parsed %s — org=%r policy_domain=%r records=%d",
        client_slug, path.name,
        report_data.org_name, report_data.policy.domain, len(report_data.records),
    )

    client = db.query(Client).filter_by(slug=client_slug, is_active=True).first()
    if not client:
        log.error("[%s] Client not found in database", client_slug)
        return False

    domain_record = db.query(Domain).filter_by(
        client_id=client.id, domain=report_data.policy.domain
    ).first()
    domain_id = domain_record.id if domain_record else None

    try:
        report = write_report(
            db=db,
            report_data=report_data,
            client_id=client.id,
            domain_id=domain_id,
            source_filename=path.name,
            checksum=checksum,
        )
        if report:
            run_intelligence(db, report)
        return report is not None
    except Exception:
        log.exception(
            "[%s] DB write failed for %s", client_slug, path.name,
        )
        db.rollback()
        return False