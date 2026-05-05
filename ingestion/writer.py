import logging
from sqlalchemy.orm import Session
from core.models import Report, Record, AuthResult, ProcessedFile, Flag
from ingestion.parser import ReportData

log = logging.getLogger(__name__)


def write_report(
    db: Session,
    report_data: ReportData,
    client_id: int,
    domain_id: int | None,
    source_filename: str,
    checksum: str,
) -> Report | None:
    """Persist a parsed DMARC report. Returns None if already ingested (dedup)."""
    if db.query(ProcessedFile).filter_by(client_id=client_id, checksum=checksum).first():
        log.info("Skipping already-processed file: %s", source_filename)
        return None

    report = Report(
        client_id=client_id,
        domain_id=domain_id,
        domain=report_data.policy.domain or report_data.org_name,
        org_name=report_data.org_name,
        org_email=report_data.org_email,
        report_id=report_data.report_id,
        begin_date=report_data.begin_date,
        end_date=report_data.end_date,
        policy_domain=report_data.policy.domain,
        policy_adkim=report_data.policy.adkim,
        policy_aspf=report_data.policy.aspf,
        policy_p=report_data.policy.p,
        policy_sp=report_data.policy.sp,
        policy_pct=report_data.policy.pct,
        source_filename=source_filename,
    )
    db.add(report)
    db.flush()

    for rec_data in report_data.records:
        record = Record(
            report_id=report.id,
            client_id=client_id,
            source_ip=rec_data.source_ip,
            count=rec_data.count,
            disposition=rec_data.disposition,
            dkim_result=rec_data.dkim_result,
            spf_result=rec_data.spf_result,
            header_from=rec_data.header_from,
            envelope_from=rec_data.envelope_from,
            envelope_to=rec_data.envelope_to,
        )
        db.add(record)
        db.flush()

        for ar in rec_data.auth_results:
            db.add(AuthResult(
                record_id=record.id,
                auth_type=ar.auth_type,
                domain=ar.domain,
                result=ar.result,
                selector=ar.selector,
            ))

    db.add(ProcessedFile(client_id=client_id, filename=source_filename, checksum=checksum))
    db.commit()
    db.refresh(report)
    log.info("Ingested report %s (%d records) for client_id=%d", report_data.report_id, len(report_data.records), client_id)
    return report