import logging
from dataclasses import dataclass
from pathlib import Path
from sqlalchemy.orm import Session
from core.config import settings
from core.models import Record
from intelligence.rules.base import BaseRule, FlagResult

log = logging.getLogger(__name__)

# ISO 3166-1 alpha-2 codes considered high-risk by default.
# Tune this list in code to suit your clients' expected sending regions.
HIGH_RISK_COUNTRIES: set[str] = {
    "KP", "IR", "RU", "CN", "NG", "UA",
}


@dataclass
class GeoData:
    country: str | None = None
    city: str | None = None
    subdivision: str | None = None
    latitude: float | None = None
    longitude: float | None = None


# Cached (reader, db_type) tuple — None means unavailable.
_state: tuple | None = None
_initialised = False


def _get_reader():
    global _state, _initialised
    if _initialised:
        return _state
    _initialised = True
    try:
        import geoip2.database
        db_path = Path(settings.geoip_db_path)
        if not db_path.exists():
            log.info("GeoIP database not found at %s — geo rules disabled (optional)", db_path)
            return None
        reader = geoip2.database.Reader(str(db_path))
        db_type = reader.metadata().database_type  # metadata() is a method in geoip2 4.x
        is_city = "City" in db_type
        _state = (reader, is_city)
        log.info("GeoIP database loaded (%s) from %s", db_type, db_path)
    except ImportError:
        log.info("geoip2 package not installed — geo rules disabled (optional)")
    return _state


def lookup_geo(ip: str) -> GeoData | None:
    """Return geo data for an IP address, or None if GeoIP is unavailable."""
    state = _get_reader()
    if state is None:
        return None
    reader, is_city = state
    try:
        if is_city:
            r = reader.city(ip)
            return GeoData(
                country=r.country.iso_code,
                city=r.city.name,
                subdivision=r.subdivisions.most_specific.name if r.subdivisions else None,
                latitude=r.location.latitude,
                longitude=r.location.longitude,
            )
        else:
            r = reader.country(ip)
            return GeoData(country=r.country.iso_code)
    except Exception:
        return None


class GeoAnomalyRule(BaseRule):
    """Flag records originating from high-risk countries."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        geo = lookup_geo(record.source_ip)
        if geo is None:
            return []

        # Enrich the record with all available geo data
        record.geo_country = geo.country
        record.geo_city = geo.city
        record.geo_subdivision = geo.subdivision
        record.geo_latitude = geo.latitude
        record.geo_longitude = geo.longitude

        if geo.country and geo.country in HIGH_RISK_COUNTRIES:
            detail: dict = {"source_ip": record.source_ip, "country": geo.country}
            if geo.city:
                detail["city"] = geo.city
            if geo.subdivision:
                detail["subdivision"] = geo.subdivision
            return [FlagResult(flag_type="geo_anomaly", severity="medium", detail=detail)]

        return []