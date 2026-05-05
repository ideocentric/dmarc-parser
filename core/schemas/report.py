from datetime import datetime
from pydantic import BaseModel


class AuthResultRead(BaseModel):
    id: int
    auth_type: str
    domain: str
    result: str
    selector: str | None

    model_config = {"from_attributes": True}


class RecordRead(BaseModel):
    id: int
    source_ip: str
    count: int
    disposition: str
    dkim_result: str
    spf_result: str
    header_from: str | None
    envelope_from: str | None
    envelope_to: str | None
    geo_country: str | None = None
    geo_city: str | None = None
    geo_subdivision: str | None = None
    geo_latitude: float | None = None
    geo_longitude: float | None = None
    whois_org: str | None = None
    whois_asn: str | None = None
    whois_as_name: str | None = None
    auth_results: list[AuthResultRead] = []
    flag_count: int = 0

    model_config = {"from_attributes": True}


class ReportRead(BaseModel):
    id: int
    domain: str
    org_name: str
    org_email: str | None
    report_id: str
    begin_date: datetime
    end_date: datetime
    policy_p: str | None
    policy_pct: int | None
    source_filename: str
    ingested_at: datetime
    record_count: int = 0

    model_config = {"from_attributes": True}


class ReportDetail(ReportRead):
    records: list[RecordRead] = []


class PaginatedReports(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReportRead]


class PaginatedRecords(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RecordRead]