import logging
from sqlalchemy.orm import Session
from core.models import Record, Flag
from intelligence.rules.geo import lookup_geo, HIGH_RISK_COUNTRIES

log = logging.getLogger(__name__)
BATCH_SIZE = 500


def enrich_geo(db: Session, client_id: int, force: bool = False) -> dict:
    """Backfill geo fields on records missing location data for a given client."""
    q = db.query(Record).filter_by(client_id=client_id)
    if not force:
        q = q.filter(Record.geo_country.is_(None))

    total = q.count()
    if total == 0:
        return {"records_scanned": 0, "records_updated": 0, "flags_added": 0}

    log.info("Geo enrichment: %d record(s) for client_id=%d (force=%s)", total, client_id, force)
    updated = 0
    flags_added = 0
    offset = 0

    while True:
        batch = q.offset(offset).limit(BATCH_SIZE).all()
        if not batch:
            break

        for record in batch:
            geo = lookup_geo(record.source_ip)
            if geo is None:
                offset += 1
                continue

            record.geo_country = geo.country
            record.geo_city = geo.city
            record.geo_subdivision = geo.subdivision
            record.geo_latitude = geo.latitude
            record.geo_longitude = geo.longitude
            updated += 1

            if geo.country and geo.country in HIGH_RISK_COUNTRIES:
                existing = db.query(Flag).filter_by(record_id=record.id, flag_type="geo_anomaly").first()
                if not existing:
                    detail: dict = {"source_ip": record.source_ip, "country": geo.country}
                    if geo.city:
                        detail["city"] = geo.city
                    db.add(Flag(
                        record_id=record.id,
                        client_id=client_id,
                        flag_type="geo_anomaly",
                        severity="medium",
                        detail=detail,
                    ))
                    flags_added += 1

        db.commit()
        offset = 0 if not force else offset + len(batch)
        if len(batch) < BATCH_SIZE:
            break

    log.info("Geo enrichment complete: %d updated, %d flag(s) added", updated, flags_added)
    return {"records_scanned": total, "records_updated": updated, "flags_added": flags_added}