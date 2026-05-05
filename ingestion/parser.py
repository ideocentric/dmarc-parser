import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
import xml.etree.ElementTree as _stdlib_ET
import defusedxml.ElementTree as ET

log = logging.getLogger(__name__)

MAX_RECORDS = 10_000           # reject reports with more records than this
MAX_COUNT_PER_RECORD = 10_000_000  # clamp absurd message counts with a warning
# Loose IP check — accepts IPv4 and IPv6; catches obviously non-IP source_ip values
_IP_RE = re.compile(
    r"^("
    r"\d{1,3}(\.\d{1,3}){3}"           # IPv4
    r"|[0-9a-fA-F:]{2,39}"              # IPv6 (simplified)
    r")$"
)
# Unix timestamp range: 2000-01-01 to 2100-01-01
_TS_MIN = 946_684_800
_TS_MAX = 4_102_444_800


@dataclass
class AuthResultData:
    auth_type: str      # "dkim" | "spf"
    domain: str
    result: str
    selector: str | None = None


@dataclass
class RecordData:
    source_ip: str
    count: int
    disposition: str
    dkim_result: str
    spf_result: str
    header_from: str | None = None
    envelope_from: str | None = None
    envelope_to: str | None = None
    auth_results: list[AuthResultData] = field(default_factory=list)


@dataclass
class PolicyPublished:
    domain: str
    adkim: str | None = None
    aspf: str | None = None
    p: str | None = None
    sp: str | None = None
    pct: int | None = None


@dataclass
class ReportData:
    org_name: str
    org_email: str | None
    report_id: str
    begin_date: datetime
    end_date: datetime
    policy: PolicyPublished
    records: list[RecordData] = field(default_factory=list)


def _text(element: _stdlib_ET.Element | None, tag: str, default: str | None = None) -> str | None:
    if element is None:
        return default
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


def _parse_timestamp(raw: str | None, field_name: str) -> datetime:
    """Convert a Unix timestamp string to datetime, with bounds validation."""
    if not raw:
        return datetime.now(timezone.utc)
    try:
        ts = int(raw)
    except (ValueError, OverflowError):
        log.warning(
            "[SECURITY] Non-integer value in %s field: %r — using current time",
            field_name, raw,
        )
        return datetime.now(timezone.utc)
    if not (_TS_MIN <= ts <= _TS_MAX):
        log.warning(
            "[SECURITY] Timestamp %d in %s is outside plausible range "
            "(%d–%d) — using current time",
            ts, field_name, _TS_MIN, _TS_MAX,
        )
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _parse_count(raw: str | None) -> int:
    """Parse message count, clamping extreme values with a warning."""
    try:
        value = int(raw or 1)
    except (ValueError, OverflowError):
        log.warning("[SECURITY] Non-integer count value %r — defaulting to 1", raw)
        return 1
    if value < 0:
        log.warning("[SECURITY] Negative count %d — defaulting to 1", value)
        return 1
    if value > MAX_COUNT_PER_RECORD:
        log.warning(
            "[SECURITY] count=%d exceeds maximum %d — clamping",
            value, MAX_COUNT_PER_RECORD,
        )
        return MAX_COUNT_PER_RECORD
    return value


def _validate_source_ip(ip: str) -> str:
    """Warn if source_ip does not look like a valid IP address."""
    if ip and not _IP_RE.match(ip):
        log.warning(
            "[SECURITY] source_ip %r does not match expected IP format — "
            "storing as-is but geo/WHOIS enrichment may fail",
            ip,
        )
    return ip


def parse_dmarc_xml(xml_string: str) -> ReportData:
    root = ET.fromstring(xml_string)

    meta = root.find("report_metadata")
    policy_el = root.find("policy_published")

    record_els = root.findall("record")
    if len(record_els) > MAX_RECORDS:
        raise ValueError(
            f"Report contains {len(record_els)} records, exceeding limit of {MAX_RECORDS}. "
            "Possible malicious or malformed report."
        )

    policy = PolicyPublished(
        domain=_text(policy_el, "domain") or "",
        adkim=_text(policy_el, "adkim"),
        aspf=_text(policy_el, "aspf"),
        p=_text(policy_el, "p"),
        sp=_text(policy_el, "sp"),
        pct=int(_text(policy_el, "pct") or 100),
    )

    records: list[RecordData] = []
    for rec_el in record_els:
        row = rec_el.find("row")
        evaluated = row.find("policy_evaluated") if row is not None else None
        identifiers = rec_el.find("identifiers")

        auth_results: list[AuthResultData] = []
        ar_el = rec_el.find("auth_results")
        if ar_el is not None:
            for dkim_el in ar_el.findall("dkim"):
                auth_results.append(AuthResultData(
                    auth_type="dkim",
                    domain=_text(dkim_el, "domain") or "",
                    result=_text(dkim_el, "result") or "unknown",
                    selector=_text(dkim_el, "selector"),
                ))
            for spf_el in ar_el.findall("spf"):
                auth_results.append(AuthResultData(
                    auth_type="spf",
                    domain=_text(spf_el, "domain") or "",
                    result=_text(spf_el, "result") or "unknown",
                ))

        raw_ip = _text(row, "source_ip") or ""
        records.append(RecordData(
            source_ip=_validate_source_ip(raw_ip),
            count=_parse_count(_text(row, "count")),
            disposition=_text(evaluated, "disposition") or "none",
            dkim_result=_text(evaluated, "dkim") or "unknown",
            spf_result=_text(evaluated, "spf") or "unknown",
            header_from=_text(identifiers, "header_from"),
            envelope_from=_text(identifiers, "envelope_from"),
            envelope_to=_text(identifiers, "envelope_to"),
            auth_results=auth_results,
        ))

    return ReportData(
        org_name=_text(meta, "org_name") or "",
        org_email=_text(meta, "email"),
        report_id=_text(meta, "report_id") or "",
        begin_date=_parse_timestamp(_text(meta, "date_range/begin"), "begin"),
        end_date=_parse_timestamp(_text(meta, "date_range/end"), "end"),
        policy=policy,
        records=records,
    )