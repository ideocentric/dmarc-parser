import logging
from pathlib import Path
from sqlalchemy.orm import Session
from core.models import Client, Domain
from ingestion.extractor import compute_checksum, extract_xml
from ingestion.geo_enrichment import enrich_geo
from ingestion.parser import parse_dmarc_xml
from ingestion.scanner import scan_bytes
from ingestion.whois_enrichment import enrich_whois
from ingestion.writer import write_report
from intelligence.engine import run_intelligence

log = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".gz", ".zip"}


def _enrich_report_records(db: Session, client_id: int, client_slug: str) -> None:
    """Geo and WHOIS enrichment for records written by the just-ingested report.

    Both enrichment functions filter to unenriched records (geo_country IS NULL,
    whois_org IS NULL), so they naturally target only the new records without
    needing an explicit report-level filter. WHOIS results are cached in
    ip_whois_cache, so repeat IPs across reports are a fast DB read.

    Failures are non-fatal — the report and intelligence flags are already
    committed before this runs.
    """
    try:
        geo = enrich_geo(db, client_id)
        if geo["records_updated"]:
            log.info("[%s] Geo enriched %d record(s)", client_slug, geo["records_updated"],
                     extra={"client": client_slug, "records_updated": geo["records_updated"],
                            "enrichment": "geo"})
    except Exception:
        log.warning("[%s] Geo enrichment failed (non-fatal)", client_slug, exc_info=True,
                    extra={"client": client_slug, "enrichment": "geo"})

    try:
        whois = enrich_whois(db, client_id)
        if whois["records_updated"]:
            log.info("[%s] WHOIS enriched %d record(s) (%d unique IP(s) queried)",
                     client_slug, whois["records_updated"], whois["ips_queried"],
                     extra={"client": client_slug, "records_updated": whois["records_updated"],
                            "ips_queried": whois["ips_queried"], "enrichment": "whois"})
    except Exception:
        log.warning("[%s] WHOIS enrichment failed (non-fatal)", client_slug, exc_info=True,
                    extra={"client": client_slug, "enrichment": "whois"})


def process_file(path: Path, client_slug: str, db: Session) -> bool:
    """
    Full ingestion pipeline for a single report file.
    Returns True if processed, False if skipped or errored.
    """
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False

    file_size = path.stat().st_size
    log.info("[%s] Processing %s (%d bytes)", client_slug, path.name, file_size,
             extra={"client": client_slug, "report_file": path.name, "file_size": file_size})

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
            extra={"client": client_slug, "report_file": path.name,
                   "file_size": file_size, "rejection_reason": str(exc)},
        )
        return False
    except Exception:
        log.exception(
            "[%s] Unexpected error extracting/parsing %s (%d bytes)",
            client_slug, path.name, file_size,
            extra={"client": client_slug, "report_file": path.name, "file_size": file_size},
        )
        return False

    log.info(
        "[%s] Parsed %s — org=%r policy_domain=%r records=%d",
        client_slug, path.name,
        report_data.org_name, report_data.policy.domain, len(report_data.records),
        extra={"client": client_slug, "report_file": path.name,
               "org": report_data.org_name, "policy_domain": report_data.policy.domain,
               "records": len(report_data.records)},
    )

    client = db.query(Client).filter_by(slug=client_slug, is_active=True).first()
    if not client:
        log.error("[%s] Client not found in database", client_slug,
                  extra={"client": client_slug})
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
            _enrich_report_records(db, client.id, client_slug)
        return report is not None
    except Exception:
        log.exception(
            "[%s] DB write failed for %s", client_slug, path.name,
            extra={"client": client_slug, "report_file": path.name},
        )
        db.rollback()
        return False