"""
Client offboarding — export and purge.

export: builds an in-memory ZIP of all client data as JSON/CSV.
purge:  cascade-deletes all client data, deactivates orphaned users,
        removes filesystem directories.

Both are super_admin-only operations called from the API and CLI.
"""
import csv
import io
import json
import logging
import shutil
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from core.config import settings as _settings
from core.models import (
    AuthResult, Client, Domain, Flag, ImapConfig,
    ProcessedFile, Record, Report, User, UserClient,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_bytes(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def build_export_zip(client: Client, db: Session) -> bytes:
    """Return a ZIP archive (bytes) of all data belonging to this client."""
    prefix = f"{client.slug}-export-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    buf = io.BytesIO()

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:

        # client.json
        zf.writestr(f"{prefix}/client.json", json.dumps({
            "id": client.id,
            "slug": client.slug,
            "name": client.name,
            "is_active": client.is_active,
            "mfa_required_admins": client.mfa_required_admins,
            "mfa_required_viewers": client.mfa_required_viewers,
            "created_at": client.created_at.isoformat(),
        }, indent=2))

        # domains.csv
        domains = db.query(Domain).filter_by(client_id=client.id).all()
        zf.writestr(f"{prefix}/domains.csv", _csv_bytes([
            {"domain": d.domain, "is_active": d.is_active, "created_at": d.created_at.isoformat()}
            for d in domains
        ]))

        # users.csv
        ucs = db.query(UserClient).filter_by(client_id=client.id).all()
        user_rows = []
        for uc in ucs:
            u = db.get(User, uc.user_id)
            if u:
                user_rows.append({
                    "email": u.email,
                    "global_role": u.role,
                    "client_role": uc.role,
                    "created_at": u.created_at.isoformat(),
                })
        zf.writestr(f"{prefix}/users.csv", _csv_bytes(user_rows))

        # imap_config.json (passwords redacted)
        imap = db.query(ImapConfig).filter_by(client_id=client.id).first()
        if imap:
            zf.writestr(f"{prefix}/imap_config.json", json.dumps({
                "auth_type": imap.auth_type,
                "host": imap.host,
                "port": imap.port,
                "username": imap.username,
                "password": "REDACTED",
                "use_ssl": imap.use_ssl,
                "inbox_folder": imap.inbox_folder,
                "processed_folder": imap.processed_folder,
                "poll_interval_minutes": imap.poll_interval_minutes,
                "is_active": imap.is_active,
                "oauth2_tenant_id": imap.oauth2_tenant_id,
                "oauth2_client_id": imap.oauth2_client_id,
                "oauth2_client_secret": "REDACTED" if imap.oauth2_client_secret else None,
                "last_polled_at": imap.last_polled_at.isoformat() if imap.last_polled_at else None,
                "last_poll_status": imap.last_poll_status,
            }, indent=2))

        # reports.csv
        reports = db.query(Report).filter_by(client_id=client.id).all()
        zf.writestr(f"{prefix}/reports.csv", _csv_bytes([
            {
                "id": r.id,
                "report_id": r.report_id,
                "domain": r.domain,
                "org_name": r.org_name,
                "org_email": r.org_email,
                "begin_date": r.begin_date.isoformat(),
                "end_date": r.end_date.isoformat(),
                "policy_domain": r.policy_domain,
                "policy_adkim": r.policy_adkim,
                "policy_aspf": r.policy_aspf,
                "policy_p": r.policy_p,
                "policy_sp": r.policy_sp,
                "policy_pct": r.policy_pct,
                "ingested_at": r.ingested_at.isoformat(),
            }
            for r in reports
        ]))

        # records.csv
        records = db.query(Record).filter_by(client_id=client.id).all()
        zf.writestr(f"{prefix}/records.csv", _csv_bytes([
            {
                "id": rec.id,
                "report_id": rec.report_id,
                "source_ip": rec.source_ip,
                "count": rec.count,
                "disposition": rec.disposition,
                "dkim_result": rec.dkim_result,
                "spf_result": rec.spf_result,
                "header_from": rec.header_from,
                "envelope_from": rec.envelope_from,
                "envelope_to": rec.envelope_to,
                "geo_country": rec.geo_country,
                "geo_city": rec.geo_city,
                "geo_subdivision": rec.geo_subdivision,
                "geo_latitude": rec.geo_latitude,
                "geo_longitude": rec.geo_longitude,
                "whois_org": rec.whois_org,
                "whois_asn": rec.whois_asn,
                "whois_as_name": rec.whois_as_name,
            }
            for rec in records
        ]))

        # auth_results.csv — joined through records
        record_ids = [r.id for r in records]
        auth_results: list[AuthResult] = []
        for i in range(0, len(record_ids), 500):  # chunk to keep IN clause manageable
            auth_results.extend(
                db.query(AuthResult)
                .filter(AuthResult.record_id.in_(record_ids[i:i + 500]))
                .all()
            )
        zf.writestr(f"{prefix}/auth_results.csv", _csv_bytes([
            {
                "id": ar.id,
                "record_id": ar.record_id,
                "auth_type": ar.auth_type,
                "domain": ar.domain,
                "result": ar.result,
                "selector": ar.selector,
            }
            for ar in auth_results
        ]))

        # flags.csv
        flags = db.query(Flag).filter_by(client_id=client.id).all()
        zf.writestr(f"{prefix}/flags.csv", _csv_bytes([
            {
                "id": f.id,
                "record_id": f.record_id,
                "flag_type": f.flag_type,
                "severity": f.severity,
                "detail_json": json.dumps(f.detail) if f.detail else "",
                "created_at": f.created_at.isoformat(),
                "acknowledged_at": f.acknowledged_at.isoformat() if f.acknowledged_at else "",
                "acknowledged_by": f.acknowledged_by or "",
            }
            for f in flags
        ]))

        # README.txt
        zf.writestr(f"{prefix}/README.txt", (
            f"DMARC Intelligence Platform — Client Data Export\n"
            f"{'=' * 50}\n\n"
            f"Client:      {client.slug} ({client.name})\n"
            f"Exported at: {datetime.now(timezone.utc).isoformat()}\n\n"
            f"Files:\n"
            f"  client.json        Client metadata\n"
            f"  domains.csv        Registered domains ({len(domains)} rows)\n"
            f"  users.csv          Users assigned to this client ({len(user_rows)} rows)\n"
            f"  imap_config.json   Mail ingestion config (passwords REDACTED)\n"
            f"  reports.csv        DMARC aggregate reports ({len(reports)} rows)\n"
            f"  records.csv        Report records / source IPs ({len(records)} rows)\n"
            f"  auth_results.csv   Per-record DKIM/SPF results ({len(auth_results)} rows)\n"
            f"  flags.csv          Intelligence flags ({len(flags)} rows)\n\n"
            f"Notes:\n"
            f"  - IMAP passwords and OAuth2 secrets are not included.\n"
            f"  - ip_whois_cache is a shared platform cache and is not included.\n"
            f"  - Raw report XML/ZIP files are not included.\n"
        ))

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Purge
# ---------------------------------------------------------------------------

def purge_client(client: Client, db: Session) -> dict:
    """
    Cascade-delete all data for this client and remove its filesystem directories.

    Runs inside a single transaction. Filesystem cleanup happens only after a
    successful commit so a DB failure leaves files intact.

    Returns a summary dict for logging and API/CLI output.
    """
    slug = client.slug
    client_id = client.id

    # Identify users whose only client assignment is this one
    assigned_user_ids = {
        uc.user_id for uc in db.query(UserClient).filter_by(client_id=client_id).all()
    }
    orphaned_user_ids = {
        uid for uid in assigned_user_ids
        if db.query(UserClient).filter(
            UserClient.user_id == uid,
            UserClient.client_id != client_id,
        ).count() == 0
    }

    # Snapshot counts for summary
    n_flags   = db.query(Flag).filter_by(client_id=client_id).count()
    n_records = db.query(Record).filter_by(client_id=client_id).count()
    n_reports = db.query(Report).filter_by(client_id=client_id).count()
    n_proc    = db.query(ProcessedFile).filter_by(client_id=client_id).count()
    n_domains = db.query(Domain).filter_by(client_id=client_id).count()
    n_imap    = db.query(ImapConfig).filter_by(client_id=client_id).count()
    n_uc      = db.query(UserClient).filter_by(client_id=client_id).count()
    n_auth    = db.query(AuthResult).filter(
        AuthResult.record_id.in_(db.query(Record.id).filter_by(client_id=client_id))
    ).count()

    # Delete in FK-safe order
    db.query(Flag).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(AuthResult).filter(
        AuthResult.record_id.in_(db.query(Record.id).filter_by(client_id=client_id))
    ).delete(synchronize_session=False)
    db.query(Record).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(ProcessedFile).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(Report).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(ImapConfig).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(Domain).filter_by(client_id=client_id).delete(synchronize_session=False)
    db.query(UserClient).filter_by(client_id=client_id).delete(synchronize_session=False)

    orphaned_emails: list[str] = []
    for uid in orphaned_user_ids:
        u = db.get(User, uid)
        if u:
            u.is_active = False
            orphaned_emails.append(u.email)

    db.delete(client)
    db.commit()

    log.warning(
        "Client %r purged — %d reports, %d records, %d flags deleted. "
        "Deactivated users: %s",
        slug, n_reports, n_records, n_flags,
        ", ".join(orphaned_emails) if orphaned_emails else "none",
    )

    # Filesystem cleanup — post-commit only
    removed_dirs: list[str] = []
    for dir_fn in (_settings.client_incoming_dir, _settings.client_archive_dir):
        try:
            p = dir_fn(slug)
            if p.exists():
                shutil.rmtree(p)
                removed_dirs.append(str(p))
        except Exception as exc:
            log.error("Failed to remove directory for %r: %s", slug, exc)

    return {
        "slug": slug,
        "purged_at": datetime.now(timezone.utc).isoformat(),
        "deleted": {
            "reports": n_reports,
            "records": n_records,
            "auth_results": n_auth,
            "flags": n_flags,
            "domains": n_domains,
            "imap_configs": n_imap,
            "processed_files": n_proc,
            "user_assignments": n_uc,
        },
        "deactivated_users": sorted(orphaned_emails),
        "filesystem_removed": removed_dirs,
    }