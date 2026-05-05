from pydantic import BaseModel


class FlagSummary(BaseModel):
    flag_type: str
    severity: str
    count: int


class IPSummary(BaseModel):
    source_ip: str
    geo_country: str | None
    geo_city: str | None
    geo_subdivision: str | None
    whois_org: str | None
    whois_asn: str | None
    total_messages: int
    report_count: int
    failure_count: int


class DailyVolume(BaseModel):
    date: str   # ISO date string YYYY-MM-DD
    total_messages: int
    pass_count: int
    fail_count: int


class ClientAnalytics(BaseModel):
    client_slug: str
    total_reports: int
    total_records: int
    total_messages: int
    open_flags: int
    flags_by_severity: dict[str, int]
    top_ips: list[IPSummary]
    daily_volume: list[DailyVolume]


class CrossClientSummary(BaseModel):
    """Super-admin view across all clients."""
    total_clients: int
    total_reports: int
    total_open_flags: int
    clients: list[ClientAnalytics]