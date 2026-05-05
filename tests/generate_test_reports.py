#!/usr/bin/env python3
"""
Test report generator — creates synthetic DMARC aggregate report files (.xml.gz)
for each intelligence scenario.

Usage:
    python tests/generate_test_reports.py [--output-dir ./test-reports] [--domain example.com]

Scenarios generated:
    all_pass.xml.gz          All records pass — baseline sender
    spf_fail.xml.gz          SPF failures under quarantine policy
    dkim_fail.xml.gz         DKIM failures under reject policy
    both_fail.xml.gz         Both DKIM and SPF fail — critical
    forwarding.xml.gz        SPF fail + DKIM pass — forwarding pattern
    policy_mismatch.xml.gz   Disposition none despite quarantine policy
    multi_sender.xml.gz      Multiple new IPs, mixed results
    realistic.xml.gz         Multi-record, multi-org, realistic mix

Expected flags per scenario are printed after generation.
"""
import argparse
import gzip
import io
import time
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(offset_days: int = 0) -> int:
    now = datetime.now(timezone.utc)
    return int(now.timestamp()) + (offset_days * 86400)


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
    begin_offset: int = -1,
    end_offset: int = 0,
) -> bytes:
    begin = _ts(begin_offset)
    end = _ts(end_offset)

    record_blocks = ""
    for rec in (records or []):
        auth_results = ""
        for ar in rec.get("dkim_results", []):
            auth_results += f"""      <dkim>
        <domain>{ar['domain']}</domain>
        <selector>{ar.get('selector', 'default')}</selector>
        <result>{ar['result']}</result>
      </dkim>\n"""
        for ar in rec.get("spf_results", []):
            auth_results += f"""      <spf>
        <domain>{ar['domain']}</domain>
        <result>{ar['result']}</result>
      </spf>\n"""

        record_blocks += f"""  <record>
    <row>
      <source_ip>{rec['source_ip']}</source_ip>
      <count>{rec['count']}</count>
      <policy_evaluated>
        <disposition>{rec.get('disposition', 'none')}</disposition>
        <dkim>{rec['eval_dkim']}</dkim>
        <spf>{rec['eval_spf']}</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>{rec.get('header_from', domain)}</header_from>
      <envelope_from>{rec.get('envelope_from', f'mail.{domain}')}</envelope_from>
    </identifiers>
    <auth_results>
{auth_results}    </auth_results>
  </record>\n"""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<feedback>
  <report_metadata>
    <org_name>{org_name}</org_name>
    <email>{org_email}</email>
    <report_id>{report_id}</report_id>
    <date_range>
      <begin>{begin}</begin>
      <end>{end}</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>{domain}</domain>
    <adkim>{adkim}</adkim>
    <aspf>{aspf}</aspf>
    <p>{policy_p}</p>
    <sp>{policy_sp}</sp>
    <pct>{policy_pct}</pct>
  </policy_published>
{record_blocks}</feedback>"""
    return xml.encode("utf-8")


def _gz(xml_bytes: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(xml_bytes)
    return buf.getvalue()


def _write(output_dir: Path, filename: str, xml_bytes: bytes) -> Path:
    dest = output_dir / filename
    dest.write_bytes(_gz(xml_bytes))
    return dest


# ---------------------------------------------------------------------------
# Scenario definitions
# ---------------------------------------------------------------------------

def scenario_all_pass(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Google LLC",
        org_email="noreply-dmarc-support@google.com",
        report_id=f"google-all-pass-{int(time.time())}",
        domain=domain,
        policy_p="none",
        records=[
            {
                "source_ip": "209.85.220.41",
                "count": 150,
                "eval_dkim": "pass",
                "eval_spf": "pass",
                "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "google", "result": "pass"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "pass"}],
            },
            {
                "source_ip": "209.85.220.42",
                "count": 50,
                "eval_dkim": "pass",
                "eval_spf": "pass",
                "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "google", "result": "pass"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "pass"}],
            },
        ],
    )
    expected = [
        "new_sender_ip (x2 — first time these IPs are seen)",
    ]
    return f"google.com!{domain}!all_pass.xml.gz", xml, expected


def scenario_spf_fail(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Microsoft Corporation",
        org_email="dmarc@microsoft.com",
        report_id=f"ms-spf-fail-{int(time.time())}",
        domain=domain,
        policy_p="quarantine",
        records=[
            {
                "source_ip": "40.107.200.103",
                "count": 25,
                "eval_dkim": "pass",
                "eval_spf": "fail",
                "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "fail"}],
            },
        ],
    )
    expected = [
        "spf_fail          [high]",
        "policy_mismatch   [medium]  — disposition=none but policy=quarantine",
        "forwarding_pattern [info]   — SPF fail + DKIM pass",
        "new_sender_ip      [low]",
    ]
    return f"microsoft.com!{domain}!spf_fail.xml.gz", xml, expected


def scenario_dkim_fail(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Mimecast Services Limited",
        org_email="dmarc-support@mimecast.com",
        report_id=f"mimecast-dkim-fail-{int(time.time())}",
        domain=domain,
        policy_p="reject",
        records=[
            {
                "source_ip": "207.211.31.120",
                "count": 8,
                "eval_dkim": "fail",
                "eval_spf": "pass",
                "disposition": "none",
                "dkim_results": [{"domain": domain, "selector": "mimecast", "result": "fail"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "pass"}],
            },
        ],
    )
    expected = [
        "dkim_fail          [high]",
        "policy_mismatch    [medium]  — disposition=none but policy=reject",
        "new_sender_ip      [low]",
    ]
    return f"mimecast.com!{domain}!dkim_fail.xml.gz", xml, expected


def scenario_both_fail(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Proofpoint Inc",
        org_email="dmarc@proofpoint.com",
        report_id=f"proofpoint-both-fail-{int(time.time())}",
        domain=domain,
        policy_p="quarantine",
        records=[
            {
                "source_ip": "148.163.130.170",
                "count": 3,
                "eval_dkim": "fail",
                "eval_spf": "fail",
                "disposition": "quarantine",
                "dkim_results": [{"domain": domain, "selector": "pphosted", "result": "fail"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "fail"}],
            },
        ],
    )
    expected = [
        "dkim_spf_both_fail  [critical]",
        "new_sender_ip       [low]",
    ]
    return f"proofpoint.com!{domain}!both_fail.xml.gz", xml, expected


def scenario_forwarding(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Mailchimp",
        org_email="dmarc@mailchimp.com",
        report_id=f"mailchimp-forwarding-{int(time.time())}",
        domain=domain,
        policy_p="quarantine",
        records=[
            {
                "source_ip": "198.2.128.180",
                "count": 12,
                "eval_dkim": "pass",
                "eval_spf": "fail",
                "disposition": "none",
                "header_from": domain,
                "dkim_results": [{"domain": domain, "selector": "k1", "result": "pass"}],
                "spf_results": [{"domain": "list-bounces.lists.example.com", "result": "fail"}],
            },
        ],
    )
    expected = [
        "spf_fail            [high]",
        "policy_mismatch     [medium]  — disposition=none but policy=quarantine",
        "forwarding_pattern  [info]    — classic forwarding: SPF fail + DKIM pass",
        "new_sender_ip       [low]",
    ]
    return f"mailchimp.com!{domain}!forwarding.xml.gz", xml, expected


def scenario_policy_mismatch(domain: str) -> tuple[str, bytes, list[str]]:
    xml = _build_xml(
        org_name="Barracuda Networks",
        org_email="dmarc@barracuda.com",
        report_id=f"barracuda-mismatch-{int(time.time())}",
        domain=domain,
        policy_p="reject",
        records=[
            {
                "source_ip": "64.235.150.100",
                "count": 5,
                "eval_dkim": "fail",
                "eval_spf": "fail",
                "disposition": "none",   # override applied
                "dkim_results": [{"domain": domain, "selector": "barracuda", "result": "fail"}],
                "spf_results": [{"domain": f"mail.{domain}", "result": "fail"}],
            },
        ],
    )
    expected = [
        "dkim_spf_both_fail  [critical]",
        "policy_mismatch     [medium]  — disposition=none override despite p=reject",
        "new_sender_ip       [low]",
    ]
    return f"barracuda.com!{domain}!policy_mismatch.xml.gz", xml, expected


def scenario_multi_sender(domain: str) -> tuple[str, bytes, list[str]]:
    """Multiple new IPs — realistic blast from a mail service."""
    ips = [
        ("198.2.128.1", 40, "pass", "pass"),
        ("198.2.128.2", 30, "pass", "fail"),
        ("198.2.128.3", 20, "fail", "pass"),
        ("198.2.128.4", 10, "fail", "fail"),
        ("198.2.128.5",  5, "pass", "pass"),
    ]
    records = []
    for ip, count, dkim, spf in ips:
        records.append({
            "source_ip": ip,
            "count": count,
            "eval_dkim": dkim,
            "eval_spf": spf,
            "disposition": "none",
            "dkim_results": [{"domain": domain, "result": dkim}],
            "spf_results": [{"domain": f"mail.{domain}", "result": spf}],
        })

    xml = _build_xml(
        org_name="Amazon SES",
        org_email="dmarc@amazon.com",
        report_id=f"ses-multi-{int(time.time())}",
        domain=domain,
        policy_p="quarantine",
        records=records,
    )
    expected = [
        "new_sender_ip       [low]     × 5 (all new IPs)",
        "spf_fail            [high]    × 2 (IPs .2 and .4)",
        "dkim_fail           [high]    × 1 (IP .3)",
        "dkim_spf_both_fail  [critical]× 1 (IP .4)",
        "forwarding_pattern  [info]    × 1 (IP .2: SPF fail + DKIM pass)",
        "policy_mismatch     [medium]  × 3 (all failures where disposition=none)",
    ]
    return f"amazon.com!{domain}!multi_sender.xml.gz", xml, expected


def scenario_realistic(domain: str) -> tuple[str, bytes, list[str]]:
    """A realistic multi-org, mixed-result report for general UI testing."""
    records = [
        {
            "source_ip": "209.85.220.41",
            "count": 500,
            "eval_dkim": "pass",
            "eval_spf": "pass",
            "disposition": "none",
            "dkim_results": [{"domain": domain, "selector": "google", "result": "pass"}],
            "spf_results": [{"domain": f"mail.{domain}", "result": "pass"}],
        },
        {
            "source_ip": "40.107.200.103",
            "count": 120,
            "eval_dkim": "pass",
            "eval_spf": "pass",
            "disposition": "none",
            "dkim_results": [{"domain": domain, "selector": "selector1", "result": "pass"}],
            "spf_results": [{"domain": f"mail.{domain}", "result": "pass"}],
        },
        {
            "source_ip": "192.0.2.55",
            "count": 3,
            "eval_dkim": "fail",
            "eval_spf": "fail",
            "disposition": "quarantine",
            "dkim_results": [{"domain": domain, "selector": "unknown", "result": "fail"}],
            "spf_results": [{"domain": "spammer.example.net", "result": "fail"}],
        },
        {
            "source_ip": "10.0.0.1",
            "count": 15,
            "eval_dkim": "pass",
            "eval_spf": "fail",
            "disposition": "none",
            "dkim_results": [{"domain": domain, "selector": "default", "result": "pass"}],
            "spf_results": [{"domain": "forwarded.example.org", "result": "fail"}],
        },
    ]
    xml = _build_xml(
        org_name="Google LLC",
        org_email="noreply-dmarc-support@google.com",
        report_id=f"google-realistic-{int(time.time())}",
        domain=domain,
        policy_p="quarantine",
        records=records,
    )
    expected = [
        "new_sender_ip       [low]     × 4",
        "dkim_spf_both_fail  [critical]× 1 (192.0.2.55)",
        "spf_fail            [high]    × 1 (10.0.0.1)",
        "forwarding_pattern  [info]    × 1 (10.0.0.1)",
    ]
    return f"google.com!{domain}!realistic.xml.gz", xml, expected


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

SCENARIOS = [
    ("all_pass",         scenario_all_pass),
    ("spf_fail",         scenario_spf_fail),
    ("dkim_fail",        scenario_dkim_fail),
    ("both_fail",        scenario_both_fail),
    ("forwarding",       scenario_forwarding),
    ("policy_mismatch",  scenario_policy_mismatch),
    ("multi_sender",     scenario_multi_sender),
    ("realistic",        scenario_realistic),
]


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic DMARC test report files")
    parser.add_argument("--output-dir", default="./test-reports", help="Directory to write .xml.gz files")
    parser.add_argument("--domain", default="example.com", help="Domain to use in policy_published")
    parser.add_argument("--scenario", choices=[s[0] for s in SCENARIOS], help="Generate a single scenario only")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected = [s for s in SCENARIOS if args.scenario is None or s[0] == args.scenario]

    print(f"\nGenerating {len(selected)} report(s) for domain '{args.domain}' → {output_dir}\n")
    print("=" * 70)

    for name, fn in selected:
        filename, xml_bytes, expected = fn(args.domain)
        dest = _write(output_dir, filename, xml_bytes)
        size = dest.stat().st_size
        print(f"\n[{name}]  {filename}  ({size} bytes)")
        print("  Expected flags:")
        for flag in expected:
            print(f"    · {flag}")

    print("\n" + "=" * 70)
    print(f"\n{len(selected)} file(s) written to {output_dir.resolve()}")
    print("\nDrop these files into your client's incoming directory:")
    print("  Docker:    docker-data/reports/incoming/<client-slug>/")
    print("  Local dev: data/reports/incoming/<client-slug>/\n")


if __name__ == "__main__":
    main()