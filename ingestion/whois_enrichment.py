"""
WHOIS / RDAP enrichment — backfills owning organisation and ASN on records.

Lookups are cached in ip_whois_cache so each unique IP is only queried once.
Run via CLI:  python -m cli.manage enrich-whois <slug>
Run via API:  POST /clients/{slug}/enrich-whois
"""
import ipaddress
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from core.models import Record, IPWhoisCache

log = logging.getLogger(__name__)
BATCH_SIZE = 200

# IP ranges that have no useful WHOIS data — skip silently
_PRIVATE_NETWORKS = [
    ipaddress.ip_network(n) for n in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
        "127.0.0.0/8", "::1/128", "fc00::/7", "fe80::/10",
    )
]


def _is_private(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        return True  # unparseable — skip


def _lookup(ip: str) -> dict | None:
    """Query RDAP for the given IP. Returns dict with org/asn/as_name/cidr or None."""
    try:
        from ipwhois import IPWhois
        from ipwhois.exceptions import IPDefinedError, WhoisLookupError
    except ImportError:
        raise RuntimeError("ipwhois is not installed — add ipwhois>=1.2.0 to requirements.txt")

    try:
        result = IPWhois(ip).lookup_rdap(depth=1)
    except IPDefinedError:
        # RFC 1918 or other special-use range — ipwhois raises this explicitly
        return None
    except WhoisLookupError as exc:
        log.warning("WHOIS lookup failed for %s: %s", ip, exc)
        return None
    except Exception as exc:
        log.warning("Unexpected WHOIS error for %s: %s", ip, exc)
        return None

    asn     = f"AS{result.get('asn')}" if result.get("asn") else None
    as_name = result.get("asn_description")
    cidr    = result.get("asn_cidr")

    # Organisation name: prefer the network entity name, fall back to ASN description
    org = None
    for entity in result.get("objects", {}).values():
        if entity.get("roles") and "registrant" in entity["roles"]:
            org = entity.get("contact", {}).get("name") or entity.get("handle")
            break
    if not org:
        # Try network name as fallback
        network = result.get("network") or {}
        org = network.get("name") or as_name

    return {"org": org, "asn": asn, "as_name": as_name, "cidr": cidr}


def _get_or_fetch(ip: str, db: Session) -> IPWhoisCache | None:
    """Return cached entry, or perform a live lookup and cache the result."""
    cached = db.query(IPWhoisCache).filter_by(source_ip=ip).first()
    if cached:
        return cached

    if _is_private(ip):
        return None

    data = _lookup(ip)
    entry = IPWhoisCache(
        source_ip=ip,
        org=data.get("org") if data else None,
        asn=data.get("asn") if data else None,
        as_name=data.get("as_name") if data else None,
        cidr=data.get("cidr") if data else None,
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    try:
        db.flush()
    except Exception:
        db.rollback()
    return entry


def enrich_whois(db: Session, client_id: int, force: bool = False) -> dict:
    """
    Backfill whois_org / whois_asn / whois_as_name on records for a client.
    Skips already-enriched records unless force=True.
    """
    q = db.query(Record).filter_by(client_id=client_id)
    if not force:
        q = q.filter(Record.whois_org.is_(None))

    total = q.count()
    if total == 0:
        return {"records_scanned": 0, "records_updated": 0, "ips_queried": 0}

    log.info("WHOIS enrichment: %d record(s) for client_id=%d (force=%s)", total, client_id, force)
    updated = 0
    ips_queried = set()
    offset = 0

    while True:
        batch = q.offset(offset).limit(BATCH_SIZE).all()
        if not batch:
            break

        for record in batch:
            entry = _get_or_fetch(record.source_ip, db)
            if entry and entry.source_ip not in ips_queried:
                ips_queried.add(entry.source_ip)

            if entry:
                record.whois_org     = entry.org
                record.whois_asn     = entry.asn
                record.whois_as_name = entry.as_name
                updated += 1

        db.commit()
        if not force:
            # Re-query picks up where we left off (enriched rows no longer appear)
            offset = 0
        else:
            offset += len(batch)
        if len(batch) < BATCH_SIZE:
            break

    log.info("WHOIS enrichment complete: %d updated, %d unique IPs queried", updated, len(ips_queried))
    return {"records_scanned": total, "records_updated": updated, "ips_queried": len(ips_queried)}