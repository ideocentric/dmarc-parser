#!/usr/bin/env python3
"""
Sample data generator for functional testing.

Produces ready-to-drop .xml.gz / .zip DMARC aggregate report files that
demonstrate every intelligence scenario in the platform UI. Files use
authentic DMARC naming conventions and realistic reporter metadata.

Usage:
    # Generate sample data for both test clients (recommended)
    python tests/generate_sample_data.py

    # Generate for a specific client/domain only
    python tests/generate_sample_data.py --client acme-test --domain acme-test.example.com

    # Custom output directory
    python tests/generate_sample_data.py --output-dir ./my-data

Output structure:
    sample-data/
    ├── acme-test/          Drop ALL files here for the acme-test client
    │   ├── *.xml.gz
    │   └── drop_files.sh   Helper — drops files in the correct order
    └── globex-test/        Drop ALL files here for the globex-test client
        └── *.xml.gz

Ingest instructions (Docker):
    bash sample-data/acme-test/drop_files.sh \\
        docker-data/reports/incoming/acme-test

    bash sample-data/globex-test/drop_files.sh \\
        docker-data/reports/incoming/globex-test
"""
import argparse
import gzip
import io
import time
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from faker import Faker

try:
    from ip_table import PROVIDER_IPS
except ImportError:
    from tests.ip_table import PROVIDER_IPS


# ---------------------------------------------------------------------------
# Deterministic fake reporter profiles
# Replaces smaller/partner company names (Mailchimp, Mimecast, Barracuda)
# with seeded Faker data. Major providers (Google, Microsoft, Yahoo,
# Proofpoint) are kept as-is since they are legitimate public email services
# that appear in real-world DMARC reports.
# ---------------------------------------------------------------------------

def _make_fake_reporters(seed: int = 42) -> dict:
    """Return deterministic fake company profiles for non-major reporters."""
    fake = Faker("en_US")
    fake.seed_instance(seed)

    def _reporter(suffix: str = "Mail Services") -> dict:
        name = fake.company().split(",")[0].split(" and ")[0].strip()
        full_name = f"{name} {suffix}"
        slug = name.lower().replace(" ", "-").replace("'", "").replace(".", "")
        domain = f"{slug}.{fake.tld()}"
        email = f"dmarc-reports@{domain}"
        return {"name": full_name, "domain": domain, "email": email}

    # Two distinct fake companies — consistent across scenarios that reuse them
    email_security_co = _reporter("Email Security")     # replaces Mailchimp
    mail_gateway_co   = _reporter("Mail Gateway")       # replaces Mimecast (×2 scenarios)
    network_sec_co    = _reporter("Network Security")   # replaces Barracuda

    return {
        "forwarding_reporter": email_security_co,   # was Mailchimp
        "dkim_fail_reporter":  mail_gateway_co,     # was Mimecast Services Limited
        "baseline_reporter":   mail_gateway_co,     # was Mimecast (same company, different file)
        "reject_reporter":     network_sec_co,      # was Barracuda Networks
    }


# ---------------------------------------------------------------------------
# Timestamp helpers — all offsets are relative to today midnight UTC
# ---------------------------------------------------------------------------

def _day_start(days_ago: int = 0) -> int:
    """Unix timestamp for midnight UTC N days ago."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((today - timedelta(days=days_ago)).timestamp())


def _day_end(days_ago: int = 0) -> int:
    return _day_start(days_ago) + 86399


# ---------------------------------------------------------------------------
# XML / file builders
# ---------------------------------------------------------------------------

def _build_xml(
    org_name: str,
    org_email: str,
    report_id: str,
    domain: str,
    policy_p: str,
    policy_sp: str = "none",
    policy_pct: int = 100,
    adkim: str = "r",
    aspf: str = "r",
    records: list[dict] | None = None,
    begin_ts: int | None = None,
    end_ts: int | None = None,
) -> bytes:
    begin = begin_ts if begin_ts is not None else _day_start(1)
    end   = end_ts   if end_ts   is not None else _day_end(0)

    record_blocks = ""
    for rec in (records or []):
        auth_xml = ""
        for ar in rec.get("dkim_results", []):
            sel = f"\n        <selector>{ar['selector']}</selector>" if ar.get("selector") else ""
            auth_xml += (
                f"      <dkim>\n"
                f"        <domain>{ar['domain']}</domain>{sel}\n"
                f"        <result>{ar['result']}</result>\n"
                f"      </dkim>\n"
            )
        for ar in rec.get("spf_results", []):
            auth_xml += (
                f"      <spf>\n"
                f"        <domain>{ar['domain']}</domain>\n"
                f"        <result>{ar['result']}</result>\n"
                f"      </spf>\n"
            )

        envelope_from = rec.get("envelope_from", f"mail.{domain}")
        envelope_to   = rec.get("envelope_to", "")
        env_to_xml    = f"      <envelope_to>{envelope_to}</envelope_to>\n" if envelope_to else ""

        record_blocks += (
            f"  <record>\n"
            f"    <row>\n"
            f"      <source_ip>{rec['source_ip']}</source_ip>\n"
            f"      <count>{rec['count']}</count>\n"
            f"      <policy_evaluated>\n"
            f"        <disposition>{rec.get('disposition', 'none')}</disposition>\n"
            f"        <dkim>{rec['eval_dkim']}</dkim>\n"
            f"        <spf>{rec['eval_spf']}</spf>\n"
            f"      </policy_evaluated>\n"
            f"    </row>\n"
            f"    <identifiers>\n"
            f"{env_to_xml}"
            f"      <envelope_from>{envelope_from}</envelope_from>\n"
            f"      <header_from>{rec.get('header_from', domain)}</header_from>\n"
            f"    </identifiers>\n"
            f"    <auth_results>\n"
            f"{auth_xml}"
            f"    </auth_results>\n"
            f"  </record>\n"
        )

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<feedback>\n"
        f"  <report_metadata>\n"
        f"    <org_name>{org_name}</org_name>\n"
        f"    <email>{org_email}</email>\n"
        f"    <report_id>{report_id}</report_id>\n"
        f"    <date_range>\n"
        f"      <begin>{begin}</begin>\n"
        f"      <end>{end}</end>\n"
        f"    </date_range>\n"
        f"  </report_metadata>\n"
        f"  <policy_published>\n"
        f"    <domain>{domain}</domain>\n"
        f"    <adkim>{adkim}</adkim>\n"
        f"    <aspf>{aspf}</aspf>\n"
        f"    <p>{policy_p}</p>\n"
        f"    <sp>{policy_sp}</sp>\n"
        f"    <pct>{policy_pct}</pct>\n"
        f"  </policy_published>\n"
        f"{record_blocks}"
        f"</feedback>"
    ).encode("utf-8")


def _write_gz(output_dir: Path, filename: str, xml_bytes: bytes) -> Path:
    dest = output_dir / filename
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(xml_bytes)
    dest.write_bytes(buf.getvalue())
    return dest


def _write_zip(output_dir: Path, filename: str, xml_bytes: bytes, inner_name: str) -> Path:
    dest = output_dir / filename
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(inner_name, xml_bytes)
    dest.write_bytes(buf.getvalue())
    return dest


def _dmarc_filename(reporter: str, domain: str, begin_ts: int, end_ts: int, ext: str = "xml.gz") -> str:
    return f"{reporter}!{domain}!{begin_ts}!{end_ts}.{ext}"


# ---------------------------------------------------------------------------
# Individual scenario builders
# Returns (filename, file_bytes, description, expected_flags, days_ago_begin)
# ---------------------------------------------------------------------------

def _make_all_pass(domain: str, days_ago: int = 2, ips: list[str] | None = None) -> dict:
    """Healthy Microsoft 365 traffic — establishes sender history."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    ip1, ip2 = (ips or ["40.107.200.103", "52.101.46.124"])[:2]
    xml = _build_xml(
        org_name="Google LLC",
        org_email="noreply-dmarc-support@google.com",
        report_id=f"google-{begin}",
        domain=domain,
        policy_p="none",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": ip1,
                "count": 45,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
            {
                "source_ip": ip2,
                "count": 12,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
            {
                "source_ip": "2a01:111:f403:c110::3",
                "count": 28,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
        ],
    )
    fname = _dmarc_filename("google.com", domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"Google — all pass (Microsoft 365 outbound: {ip1}, {ip2}, IPv6)",
        "flags": ["new_sender_ip × 3 [low]"],
        "days_ago": days_ago,
    }


def _make_outlook_all_pass(
    domain: str, days_ago: int = 2, spike_ip: str = "40.107.12.205", ip2: str = "40.107.89.153"
) -> dict:
    """Outlook.com healthy report — adds sender history for volume spike IP."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    xml = _build_xml(
        org_name="Outlook.com",
        org_email="dmarcreport@microsoft.com",
        report_id=f"outlook-{begin}",
        domain=domain,
        policy_p="none",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                # This IP will appear again in the volume spike scenario
                "source_ip": spike_ip,
                "count": 18,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
                "envelope_to": "outlook.com",
            },
            {
                "source_ip": ip2,
                "count": 6,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
                "envelope_to": "outlook.com",
            },
        ],
    )
    fname = _dmarc_filename("protection.outlook.com", domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"Outlook.com — all pass (baseline for volume spike IP {spike_ip})",
        "flags": ["new_sender_ip × 2 [low]"],
        "days_ago": days_ago,
    }


def _make_mimecast_all_pass(
    domain: str, reporter: dict, days_ago: int = 2, ips: list[str] | None = None
) -> dict:
    """Mail gateway reporter — all pass with realistic multi-record report."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    ip1, ip2 = (ips or ["40.107.201.131", "52.101.52.126"])[:2]
    # Use the reporter's net TLD variant to give the baseline file a distinct name
    net_domain = reporter["domain"].replace(f".{reporter['domain'].split('.')[-1]}", ".net")
    xml = _build_xml(
        org_name=reporter["name"],
        org_email=f"no-reply@{net_domain}",
        report_id=f"{reporter['domain'].split('.')[0]}-{begin}",
        domain=domain,
        policy_p="none",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": ip1,
                "count": 3,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
            {
                "source_ip": ip2,
                "count": 5,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
        ],
    )
    fname = f"{net_domain}!{domain}!{begin}!{end}!sampledata.xml.gz"
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"{reporter['name']} — all pass (2 records, baseline)",
        "flags": ["new_sender_ip × 2 [low]"],
        "days_ago": days_ago,
    }


def _make_forwarding_spf_fail(domain: str, reporter: dict, days_ago: int = 1) -> dict:
    """Classic email forwarding — SPF fails but DKIM passes. Triggers forwarding_pattern + spf_fail."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    spf_envelope = f"lists.{reporter['domain']}"
    xml = _build_xml(
        org_name=reporter["name"],
        org_email=reporter["email"],
        report_id=f"{reporter['domain'].split('.')[0]}-fwd-{begin}",
        domain=domain,
        policy_p="quarantine",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": "198.2.128.180",
                "count": 14,
                "eval_dkim": "pass", "eval_spf": "fail", "disposition": "none",
                "header_from": domain,
                "envelope_from": f"bounce.lists.{domain}",
                "dkim_results": [{"domain": domain, "selector": "k1", "result": "pass"}],
                "spf_results":  [{"domain": spf_envelope, "result": "fail"}],
            },
            {
                "source_ip": "198.2.128.181",
                "count": 8,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "k1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
        ],
    )
    fname = _dmarc_filename(reporter["domain"], domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"{reporter['name']} — forwarding pattern (SPF fail + DKIM pass, p=quarantine)",
        "flags": [
            "spf_fail [high] — 198.2.128.180",
            "forwarding_pattern [info] — SPF fail + DKIM pass is the classic forwarding signature",
            "policy_mismatch [medium] — disposition=none despite p=quarantine",
            "new_sender_ip [low] × 2",
        ],
        "days_ago": days_ago,
    }


def _make_dkim_fail_only(domain: str, reporter: dict, days_ago: int = 1) -> dict:
    """DKIM fails but SPF passes — misconfigured signing key or replay attempt."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    slug = reporter["domain"].split(".")[0]
    xml = _build_xml(
        org_name=reporter["name"],
        org_email=reporter["email"],
        report_id=f"{slug}-dkimfail-{begin}",
        domain=domain,
        policy_p="reject",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": "207.211.31.120",
                "count": 7,
                "eval_dkim": "fail", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": slug, "result": "fail"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
        ],
    )
    fname = _dmarc_filename(reporter["domain"], domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"{reporter['name']} — DKIM fail only (SPF passes), p=reject policy",
        "flags": [
            "dkim_fail [high]",
            "policy_mismatch [medium] — disposition=none despite p=reject",
            "new_sender_ip [low]",
        ],
        "days_ago": days_ago,
    }


def _make_both_fail_quarantine(
    domain: str, days_ago: int = 1, proofpoint_ip: str = "148.163.130.170"
) -> dict:
    """Both DKIM and SPF fail under quarantine policy — critical severity."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    xml = _build_xml(
        org_name="Proofpoint Inc",
        org_email="dmarc@proofpoint.com",
        report_id=f"proofpoint-bothfail-{begin}",
        domain=domain,
        policy_p="quarantine",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": proofpoint_ip,
                "count": 4,
                "eval_dkim": "fail", "eval_spf": "fail", "disposition": "quarantine",
                "dkim_results": [{"domain": domain, "selector": "pphosted", "result": "fail"}],
                "spf_results":  [{"domain": "spammer.example.net", "result": "fail"}],
            },
        ],
    )
    fname = _dmarc_filename("proofpoint.com", domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": "Proofpoint — both DKIM and SPF fail, p=quarantine (spoofing attempt quarantined)",
        "flags": [
            "dkim_spf_both_fail [critical]",
            "new_sender_ip [low]",
        ],
        "days_ago": days_ago,
    }


def _make_both_fail_reject(domain: str, reporter: dict, days_ago: int = 0) -> dict:
    """Both fail under reject policy — most severe configuration, disposition override."""
    begin, end = _day_start(days_ago), _day_end(days_ago)
    slug = reporter["domain"].split(".")[0]
    xml = _build_xml(
        org_name=reporter["name"],
        org_email=reporter["email"],
        report_id=f"{slug}-bothfail-{begin}",
        domain=domain,
        policy_p="reject",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": "64.235.150.100",
                "count": 2,
                "eval_dkim": "fail", "eval_spf": "fail", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": slug, "result": "fail"}],
                "spf_results":  [{"domain": "suspicious.example.org", "result": "fail"}],
            },
        ],
    )
    fname = _dmarc_filename(reporter["domain"], domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"{reporter['name']} — both fail, p=reject, disposition overridden to none (policy_mismatch)",
        "flags": [
            "dkim_spf_both_fail [critical]",
            "policy_mismatch [medium] — disposition=none despite p=reject",
            "new_sender_ip [low]",
        ],
        "days_ago": days_ago,
    }


def _make_volume_spike(domain: str, days_ago: int = 0, spike_ip: str = "40.107.12.205") -> dict:
    """
    High message volume from an IP previously seen at ~18 messages.
    Requires _make_outlook_all_pass() to have been ingested first so that
    spike_ip has historical data (avg=18). This report sends 200
    messages from the same IP — 200 >= 18*5=90 → volume_spike fires.
    """
    begin, end = _day_start(days_ago), _day_end(days_ago)
    xml = _build_xml(
        org_name="Enterprise Outlook",
        org_email="dmarcreport@microsoft.com",
        report_id=f"enterprise-outlook-spike-{begin}",
        domain=domain,
        policy_p="none",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                # Same IP as in _make_outlook_all_pass baseline — historical avg = 18
                "source_ip": spike_ip,
                "count": 200,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
                "envelope_to": "outlook.com",
            },
            {
                "source_ip": "2a01:111:f403:c007::2",
                "count": 15,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
                "envelope_to": "outlook.com",
            },
        ],
    )
    fname = _dmarc_filename("enterprise.protection.outlook.com", domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": f"Enterprise Outlook — volume spike ({spike_ip} sends 200 vs historical ~18)",
        "flags": [
            f"volume_spike [medium] — {spike_ip} sent 200 messages (historical avg ~18, threshold 5×)",
            "new_sender_ip [low] — 2a01:111:f403:c007::2 (first time seen)",
            "NOTE: volume_spike requires the Outlook baseline file to be ingested first",
        ],
        "days_ago": days_ago,
    }


def _make_geo_anomaly(domain: str, days_ago: int = 0, geo_entry: dict | None = None) -> dict:
    """
    Both DKIM and SPF fail from a geo-anomalous IP.
    Triggers geo_anomaly [medium] IF GeoIP database is configured.
    The dkim_spf_both_fail [critical] fires regardless.
    Default entry: Russia / 5.44.42.1 (IQ-NET LLC).
    """
    if geo_entry is None:
        geo_entry = {"ip": "5.44.42.1", "country": "RU", "country_name": "Russia"}
    geo_ip = geo_entry["ip"]
    country = geo_entry["country"]
    country_name = geo_entry["country_name"]
    begin, end = _day_start(days_ago), _day_end(days_ago)
    xml = _build_xml(
        org_name="Yahoo",
        org_email="dmarchelp@yahooinc.com",
        report_id=f"yahoo-geo-{begin}",
        domain=domain,
        policy_p="reject",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                "source_ip": geo_ip,
                "count": 1,
                "eval_dkim": "fail", "eval_spf": "fail", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "unknown", "result": "fail"}],
                "spf_results":  [{"domain": f"mail.suspicious.{country.lower()}", "result": "fail"}],
            },
        ],
    )
    fname = _dmarc_filename("yahoo.com", domain, begin, end)
    return {
        "filename": fname,
        "bytes": xml,
        "format": "gz",
        "description": (
            f"Yahoo — both fail from {country_name} IP {geo_ip} "
            f"({country}, geo_anomaly if GeoIP configured)"
        ),
        "flags": [
            "dkim_spf_both_fail [critical]",
            "policy_mismatch [medium] — disposition=none despite p=reject",
            f"geo_anomaly [medium] — {geo_ip} ({country_name}/{country}), "
            "only if GeoLite2-City.mmdb is present",
            "new_sender_ip [low]",
        ],
        "days_ago": days_ago,
    }


def _make_mixed_realistic(
    domain: str, days_ago: int = 0, google_fwd_ip: str = "209.85.134.103"
) -> dict:
    """
    Google report with a realistic mix of records — the kind of daily report
    a Microsoft 365 organisation typically receives from Google's DMARC scanner.
    Includes one forwarded email (SPF fail + DKIM pass), bulk clean traffic,
    and one complete authentication failure.
    """
    begin, end = _day_start(days_ago), _day_end(days_ago)
    xml = _build_xml(
        org_name="google.com",
        org_email="noreply-dmarc-support@google.com",
        report_id=f"google-realistic-{begin}",
        domain=domain,
        policy_p="none",
        begin_ts=begin,
        end_ts=end,
        records=[
            {
                # Bulk legitimate outbound via M365
                "source_ip": "2a01:111:f403:c110::3",
                "count": 38,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
            {
                "source_ip": "2a01:111:f403:c105::7",
                "count": 22,
                "eval_dkim": "pass", "eval_spf": "pass", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": domain, "result": "pass"}],
            },
            {
                # Google forwarding — SPF evaluates against the forwarding server
                "source_ip": google_fwd_ip,
                "count": 6,
                "eval_dkim": "pass", "eval_spf": "fail", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results":  [{"domain": "harbor-fund.org", "result": "pass"}],
            },
            {
                # Unknown sender, both fail — possible spoofing attempt
                "source_ip": "2a01:111:f403:e013::",
                "count": 1,
                "eval_dkim": "fail", "eval_spf": "fail", "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "fail"}],
                "spf_results":  [{"domain": "7lyonsmedia.com", "result": "softfail"}],
            },
        ],
    )
    fname = _dmarc_filename("google.com", domain, begin, end, ext="zip")
    return {
        "filename": fname,
        "bytes": xml,
        "format": "zip",
        "description": "Google — realistic mixed report (ZIP format): bulk pass + forwarding + one both-fail",
        "flags": [
            f"forwarding_pattern [info] — {google_fwd_ip} (SPF fail + DKIM pass)",
            f"spf_fail [high] — {google_fwd_ip}",
            "dkim_spf_both_fail [critical] — 2a01:111:f403:e013::",
            "new_sender_ip [low] × 4",
        ],
        "days_ago": days_ago,
    }


# ---------------------------------------------------------------------------
# Client scenario sets
# ---------------------------------------------------------------------------

def scenarios_for_client(domain: str, reporters: dict) -> list[dict]:
    """
    Full scenario set for one client. Files are ordered so that baseline
    records (which enable volume_spike detection) come before the spike file.
    All baseline files use days_ago >= 2; scenario files use days_ago 0-1.

    IPs are sourced from PROVIDER_IPS (tests/ip_table.py — real provider ranges
    from live SPF/MX lookups). The volume spike baseline and spike share the
    same M365 IP so the platform's historical-average check fires correctly.
    """
    _m365       = PROVIDER_IPS["microsoft_365"]
    _google     = PROVIDER_IPS["google_workspace"]
    _proofpoint = PROVIDER_IPS["proofpoint"]
    _geo        = PROVIDER_IPS["geo_anomaly"]

    # M365 IP shared between baseline and spike — must be identical in both files
    spike_ip = _m365[3]["ip"]   # 40.107.12.205 (40.107.0.0/16)

    return [
        # ── Baseline files (days_ago=2) — must be ingested first ──────────
        _make_all_pass(domain, days_ago=2,
                       ips=[_m365[0]["ip"], _m365[1]["ip"]]),
        _make_outlook_all_pass(domain, days_ago=2,
                               spike_ip=spike_ip, ip2=_m365[4]["ip"]),
        _make_mimecast_all_pass(domain, reporters["baseline_reporter"], days_ago=2,
                                ips=[_m365[6]["ip"], _m365[7]["ip"]]),
        # ── Scenario files (days_ago=0-1) ─────────────────────────────────
        _make_forwarding_spf_fail(domain, reporters["forwarding_reporter"], days_ago=1),
        _make_dkim_fail_only(domain, reporters["dkim_fail_reporter"], days_ago=1),
        _make_both_fail_quarantine(domain, days_ago=1,
                                   proofpoint_ip=_proofpoint[0]["ip"]),
        _make_both_fail_reject(domain, reporters["reject_reporter"], days_ago=0),
        _make_volume_spike(domain, days_ago=0, spike_ip=spike_ip),
        _make_geo_anomaly(domain, days_ago=0, geo_entry=_geo[0]),
        _make_mixed_realistic(domain, days_ago=0,
                              google_fwd_ip=_google[3]["ip"]),
    ]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _write_file(output_dir: Path, scenario: dict) -> Path:
    fname = scenario["filename"]
    xml_bytes = scenario["bytes"]
    if scenario["format"] == "zip":
        inner = fname.replace(".zip", ".xml")
        return _write_zip(output_dir, fname, xml_bytes, inner)
    else:
        return _write_gz(output_dir, fname, xml_bytes)


def _write_drop_script(output_dir: Path, scenarios: list[dict], target_note: str):
    """Write a helper shell script that drops files in the correct order."""
    lines = [
        "#!/usr/bin/env bash",
        "#",
        "# Drop sample DMARC files into an ingest folder in the correct order.",
        "# Baseline files (days_ago=2) are dropped first so the volume_spike rule",
        "# has historical data to compare against.",
        "#",
        "# Usage:",
        f"#   bash drop_files.sh <path-to-incoming-folder>",
        "#",
        "# Example (Docker):",
        f"#   bash drop_files.sh docker-data/reports/incoming/{target_note}",
        "#",
        "DEST=${1:?Usage: $0 <destination-folder>}",
        'mkdir -p "$DEST"',
        "",
        "# Baseline files — drop first",
    ]
    baselines = [s for s in scenarios if s["days_ago"] >= 2]
    rest      = [s for s in scenarios if s["days_ago"] < 2]
    for s in baselines:
        lines.append(f'cp "{s["filename"]}" "$DEST/" && echo "  dropped: {s["filename"]}"')
    lines += ["", "sleep 3   # give the watcher time to process baseline files", ""]
    lines.append("# Scenario files — drop after baseline is ingested")
    for s in rest:
        lines.append(f'cp "{s["filename"]}" "$DEST/" && echo "  dropped: {s["filename"]}"')
        lines.append("sleep 2")
    lines += ["", 'echo ""', 'echo "All files dropped. Check the watcher log and UI."']

    script = output_dir / "drop_files.sh"
    script.write_text("\n".join(lines) + "\n")
    script.chmod(0o755)
    return script


def _print_manifest(client_slug: str, scenarios: list[dict], output_dir: Path):
    print(f"\n{'=' * 72}")
    print(f"  Client: {client_slug}   →  {output_dir.resolve()}")
    print(f"{'=' * 72}")
    for s in scenarios:
        size = (output_dir / s["filename"]).stat().st_size
        tag = "BASELINE" if s["days_ago"] >= 2 else "SCENARIO"
        print(f"\n  [{tag}]  {s['filename']}  ({size}B)")
        print(f"  {s['description']}")
        print("  Flags:")
        for f in s["flags"]:
            print(f"    · {f}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

CLIENT_DEFAULTS = [
    {"slug": "acme-test",   "domain": "acme-test.example.com"},
    {"slug": "globex-test", "domain": "globex-demo.com"},
]


def main():
    parser = argparse.ArgumentParser(
        description="Generate sample DMARC report files for functional testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--client", default=None,
        help="Client slug to generate for (default: both acme-test and globex-test)",
    )
    parser.add_argument(
        "--domain", default=None,
        help="Domain to use in reports (required if --client is specified)",
    )
    parser.add_argument(
        "--output-dir", default="./sample-data",
        help="Root output directory (default: ./sample-data)",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Faker seed for deterministic fake reporter names (default: 42)",
    )
    args = parser.parse_args()

    output_root = Path(args.output_dir)
    reporters = _make_fake_reporters(seed=args.seed)

    if args.client:
        if not args.domain:
            parser.error("--domain is required when --client is specified")
        clients = [{"slug": args.client, "domain": args.domain}]
    else:
        clients = CLIENT_DEFAULTS

    print(f"\nGenerating sample DMARC data → {output_root.resolve()}  (seed={args.seed})")

    for c in clients:
        slug   = c["slug"]
        domain = c["domain"]
        out    = output_root / slug
        out.mkdir(parents=True, exist_ok=True)

        scenarios = scenarios_for_client(domain, reporters)

        for s in scenarios:
            _write_file(out, s)

        _write_drop_script(out, scenarios, slug)
        _print_manifest(slug, scenarios, out)

    print("=" * 72)
    print("\nTo ingest (Docker):")
    for c in clients:
        slug = c["slug"]
        print(f"  cd {output_root}/{slug} && bash drop_files.sh docker-data/reports/incoming/{slug}")
    print()
    print("To ingest (local dev):")
    for c in clients:
        slug = c["slug"]
        print(f"  cd {output_root}/{slug} && bash drop_files.sh data/reports/incoming/{slug}")
    print()
    print("Or use mgr scan after copying all files (processes in filesystem order):")
    for c in clients:
        slug = c["slug"]
        print(f"  mgr scan {slug}")
    print()


if __name__ == "__main__":
    main()