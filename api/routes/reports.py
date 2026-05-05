from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.deps import get_db, get_accessible_client
from core.models import Client, Report, Record, Flag, AuthResult
from core.schemas.report import (
    ReportRead, ReportDetail, RecordRead, AuthResultRead,
    PaginatedReports, PaginatedRecords,
)

router = APIRouter(prefix="/clients/{slug}/reports", tags=["reports"])
records_router = APIRouter(prefix="/clients/{slug}/records", tags=["reports"])


def _record_to_read(rec: Record, db: Session) -> RecordRead:
    flag_count = db.query(func.count(Flag.id)).filter_by(record_id=rec.id).scalar() or 0
    return RecordRead(
        id=rec.id,
        source_ip=rec.source_ip,
        count=rec.count,
        disposition=rec.disposition,
        dkim_result=rec.dkim_result,
        spf_result=rec.spf_result,
        header_from=rec.header_from,
        envelope_from=rec.envelope_from,
        envelope_to=rec.envelope_to,
        geo_country=rec.geo_country,
        geo_city=rec.geo_city,
        geo_subdivision=rec.geo_subdivision,
        geo_latitude=rec.geo_latitude,
        geo_longitude=rec.geo_longitude,
        whois_org=rec.whois_org,
        whois_asn=rec.whois_asn,
        whois_as_name=rec.whois_as_name,
        auth_results=[
            AuthResultRead(id=ar.id, auth_type=ar.auth_type, domain=ar.domain,
                           result=ar.result, selector=ar.selector)
            for ar in rec.auth_results
        ],
        flag_count=flag_count,
    )


def _report_to_read(report: Report, db: Session) -> ReportRead:
    record_count = db.query(func.count(Record.id)).filter_by(report_id=report.id).scalar() or 0
    return ReportRead(
        id=report.id,
        domain=report.domain,
        org_name=report.org_name,
        org_email=report.org_email,
        report_id=report.report_id,
        begin_date=report.begin_date,
        end_date=report.end_date,
        policy_p=report.policy_p,
        policy_pct=report.policy_pct,
        source_filename=report.source_filename,
        ingested_at=report.ingested_at,
        record_count=record_count,
    )


@router.get("", response_model=PaginatedReports)
def list_reports(
    slug: str,
    domain: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    q = db.query(Report).filter_by(client_id=client.id)
    if domain:
        q = q.filter(Report.domain == domain)
    total = q.count()
    reports = q.order_by(Report.end_date.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedReports(total=total, page=page, page_size=page_size,
                            items=[_report_to_read(r, db) for r in reports])


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(
    slug: str,
    report_id: int,
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    report = db.query(Report).filter_by(id=report_id, client_id=client.id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
    base = _report_to_read(report, db)
    return ReportDetail(**base.model_dump(), records=[_record_to_read(r, db) for r in report.records])


@records_router.get("", response_model=PaginatedRecords)
def list_records(
    slug: str,
    source_ip: str | None = Query(None),
    disposition: str | None = Query(None),
    dkim_result: str | None = Query(None),
    spf_result: str | None = Query(None),
    geo_country: str | None = Query(None),
    has_flags: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    q = db.query(Record).filter_by(client_id=client.id)
    if source_ip:
        q = q.filter(Record.source_ip == source_ip)
    if disposition:
        q = q.filter(Record.disposition == disposition)
    if dkim_result:
        q = q.filter(Record.dkim_result == dkim_result)
    if spf_result:
        q = q.filter(Record.spf_result == spf_result)
    if geo_country:
        q = q.filter(Record.geo_country == geo_country)
    if has_flags is True:
        q = q.filter(Record.flags.any())
    elif has_flags is False:
        q = q.filter(~Record.flags.any())

    total = q.count()
    records = q.order_by(Record.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedRecords(total=total, page=page, page_size=page_size,
                            items=[_record_to_read(r, db) for r in records])