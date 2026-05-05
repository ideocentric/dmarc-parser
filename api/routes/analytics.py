from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from api.deps import get_db, get_accessible_client, require_super_admin
from core.models import Client, User, Report, Record, Flag
from core.schemas.analytics import ClientAnalytics, CrossClientSummary, IPSummary, DailyVolume

router = APIRouter(prefix="/clients/{slug}/analytics", tags=["analytics"])
cross_router = APIRouter(prefix="/analytics", tags=["analytics"])


def _build_analytics(db: Session, client_id: int, client_slug: str) -> ClientAnalytics:
    total_reports = db.query(func.count(Report.id)).filter_by(client_id=client_id).scalar() or 0
    total_records = db.query(func.count(Record.id)).filter_by(client_id=client_id).scalar() or 0
    total_messages = db.query(func.sum(Record.count)).filter_by(client_id=client_id).scalar() or 0
    open_flags = (
        db.query(func.count(Flag.id))
        .filter_by(client_id=client_id)
        .filter(Flag.acknowledged_at.is_(None))
        .scalar() or 0
    )

    severity_rows = (
        db.query(Flag.severity, func.count(Flag.id))
        .filter_by(client_id=client_id)
        .filter(Flag.acknowledged_at.is_(None))
        .group_by(Flag.severity)
        .all()
    )
    flags_by_severity = {row[0]: row[1] for row in severity_rows}

    ip_rows = (
        db.query(
            Record.source_ip,
            func.max(Record.geo_country).label("geo_country"),
            func.max(Record.geo_city).label("geo_city"),
            func.max(Record.geo_subdivision).label("geo_subdivision"),
            func.max(Record.whois_org).label("whois_org"),
            func.max(Record.whois_asn).label("whois_asn"),
            func.sum(Record.count).label("total_messages"),
            func.count(Record.id).label("report_count"),
        )
        .filter_by(client_id=client_id)
        .group_by(Record.source_ip)
        .order_by(func.sum(Record.count).desc())
        .limit(10)
        .all()
    )
    top_ips = []
    for row in ip_rows:
        fail_count = (
            db.query(func.count(Record.id))
            .filter(
                Record.client_id == client_id,
                Record.source_ip == row.source_ip,
                (Record.dkim_result != "pass") | (Record.spf_result != "pass"),
            )
            .scalar() or 0
        )
        top_ips.append(IPSummary(
            source_ip=row.source_ip,
            geo_country=row.geo_country,
            geo_city=row.geo_city,
            geo_subdivision=row.geo_subdivision,
            whois_org=row.whois_org,
            whois_asn=row.whois_asn,
            total_messages=row.total_messages,
            report_count=row.report_count,
            failure_count=fail_count,
        ))

    # cast(DateTime, Date) works in both SQLite and PostgreSQL
    date_col = cast(Report.begin_date, Date)
    daily_rows = (
        db.query(date_col.label("date"), func.sum(Record.count).label("total_messages"))
        .join(Record, Record.report_id == Report.id)
        .filter(Report.client_id == client_id)
        .group_by(date_col)
        .order_by(date_col.desc())
        .limit(30)
        .all()
    )
    daily_volume = [
        DailyVolume(date=str(row.date), total_messages=row.total_messages or 0, pass_count=0, fail_count=0)
        for row in reversed(daily_rows)
    ]

    return ClientAnalytics(
        client_slug=client_slug,
        total_reports=total_reports,
        total_records=total_records,
        total_messages=total_messages,
        open_flags=open_flags,
        flags_by_severity=flags_by_severity,
        top_ips=top_ips,
        daily_volume=daily_volume,
    )


@router.get("", response_model=ClientAnalytics)
def client_analytics(
    slug: str,
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    return _build_analytics(db, client.id, slug)


@router.get("/geo-distribution")
def geo_distribution(
    slug: str,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    client: Client = Depends(get_accessible_client),
):
    """Message volume grouped by country for the given time window."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.query(
            Record.geo_country,
            func.sum(Record.count).label("messages"),
        )
        .join(Report, Record.report_id == Report.id)
        .filter(
            Record.client_id == client.id,
            Record.geo_country.isnot(None),
            Report.begin_date >= cutoff,
        )
        .group_by(Record.geo_country)
        .order_by(func.sum(Record.count).desc())
        .all()
    )
    return [
        {"country": row.geo_country, "messages": int(row.messages or 0)}
        for row in rows
    ]


@cross_router.get("", response_model=CrossClientSummary)
def cross_client_analytics(db: Session = Depends(get_db), _: User = Depends(require_super_admin)):
    clients = db.query(Client).filter_by(is_active=True).all()
    client_list = []
    total_reports = 0
    total_open_flags = 0

    for client in clients:
        analytics = _build_analytics(db, client.id, client.slug)
        client_list.append(analytics)
        total_reports += analytics.total_reports
        total_open_flags += analytics.open_flags

    return CrossClientSummary(
        total_clients=len(clients),
        total_reports=total_reports,
        total_open_flags=total_open_flags,
        clients=client_list,
    )