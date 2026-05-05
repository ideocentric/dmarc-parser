#!/usr/bin/env python3
"""
Build the IP address table used by generate_sample_data.py.

Queries SPF TXT records and MX hostnames for major email providers,
samples representative IPv4 addresses from each CIDR range, and writes
tests/ip_table.py as a committed static module.

Run this periodically (e.g. quarterly) when provider IP ranges change,
or when WHOIS/geo enrichment lookups stop matching expected results.

Usage:
    python tests/build_ip_table.py              # refresh all, write ip_table.py
    python tests/build_ip_table.py --dry-run    # print table without writing
    python tests/build_ip_table.py --provider microsoft_365

Requires: dnspython>=2.6.0
"""
import argparse
import ipaddress
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import dns.resolver
    import dns.rdatatype
    import dns.exception
except ImportError:
    sys.exit("dnspython is required: pip install dnspython")

# ---------------------------------------------------------------------------
# Provider → SPF record lookup targets
# ---------------------------------------------------------------------------

SPF_SOURCES = {
    "microsoft_365":   "spf.protection.outlook.com",
    "google_workspace": "_spf.google.com",
    "amazon_ses":      "amazonses.com",
}

MX_SOURCES = {
    "yahoo": "yahoo.com",
}

# ---------------------------------------------------------------------------
# Proofpoint — manual entries (no public SPF at _spf.proofpoint.com)
# Source: Proofpoint's published outbound relay range 148.163.0.0/16
# ---------------------------------------------------------------------------

PROOFPOINT_MANUAL = [
    {"ip": "148.163.130.170", "cidr": "148.163.0.0/16", "source": "Proofpoint documented range"},
    {"ip": "148.163.7.43",    "cidr": "148.163.0.0/16", "source": "Proofpoint documented range"},
    {"ip": "148.163.200.19",  "cidr": "148.163.0.0/16", "source": "Proofpoint documented range"},
]

# ---------------------------------------------------------------------------
# Geo-anomaly IPs — hardcoded with verified country assignment
# These are publicly-routed IPv4 addresses assigned to the named country.
# Used by the geo_anomaly intelligence rule scenario in generate_sample_data.py.
# ---------------------------------------------------------------------------

GEO_ANOMALY_IPS = [
    {
        "ip": "5.44.42.1",
        "country": "RU",
        "country_name": "Russia",
        "asn": "AS41805",
        "note": "IQ-NET LLC, publicly routed Russian address block",
    },
    {
        "ip": "175.45.176.5",
        "country": "KP",
        "country_name": "North Korea",
        "asn": "AS131279",
        "note": "Star JV (state ISP), one of the few DPRK-assigned IPv4 ranges (175.45.176.0/22)",
    },
    {
        "ip": "31.2.128.1",
        "country": "IR",
        "country_name": "Iran",
        "asn": "AS48159",
        "note": "Telecommunications Company of Iran (TCI/Aria Shatel), 31.2.0.0/18",
    },
    {
        "ip": "178.172.160.1",
        "country": "BY",
        "country_name": "Belarus",
        "asn": "AS6697",
        "note": "Beltelecom (Belarusian state telecoms provider), 178.172.128.0/18",
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query_spf(domain: str) -> str | None:
    """Return the SPF TXT record for domain, or None if not found."""
    try:
        answers = dns.resolver.resolve(domain, "TXT")
        for rdata in answers:
            txt = b"".join(rdata.strings).decode("utf-8", errors="replace")
            if txt.startswith("v=spf1"):
                return txt
    except (dns.exception.DNSException, Exception):
        pass
    return None


def _parse_ipv4_cidrs(spf: str) -> list[tuple[str, str]]:
    """Extract (cidr, source_domain) pairs from an SPF record, IPv4 only."""
    results = []
    for token in spf.split():
        if token.startswith("ip4:"):
            cidr = token[4:]
            try:
                ipaddress.IPv4Network(cidr, strict=False)
                results.append(cidr)
            except ValueError:
                pass
    return results


def _sample_ips(cidr: str, n: int = 3) -> list[str]:
    """
    Return up to n representative host IPs from a CIDR block.
    Uses fixed offsets so the output is deterministic across runs.
    Offsets chosen to land in the middle of typical /24 subnets within the range.
    """
    net = ipaddress.IPv4Network(cidr, strict=False)
    hosts = list(net.hosts())
    if not hosts:
        return []

    # Offsets as fractions of the total host count — gives spread across the range
    total = len(hosts)
    offsets = [
        int(total * 0.05),
        int(total * 0.35),
        int(total * 0.65),
        int(total * 0.85),
    ]
    seen = set()
    result = []
    for off in offsets:
        idx = min(off, total - 1)
        ip = str(hosts[idx])
        if ip not in seen:
            seen.add(ip)
            result.append(ip)
        if len(result) >= n:
            break
    return result


def _resolve_mx_ips(domain: str, limit: int = 4) -> list[tuple[str, str]]:
    """Resolve MX records for domain to IPv4 addresses. Returns (ip, hostname) pairs."""
    results = []
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        for mx in sorted(mx_records, key=lambda r: r.preference):
            hostname = str(mx.exchange).rstrip(".")
            try:
                a_answer = dns.resolver.resolve(hostname, "A")
                for rdata in a_answer:
                    # dnspython 2.x: A records expose .address attribute
                    ip = getattr(rdata, "address", None) or str(rdata)
                    results.append((ip, hostname))
                    if len(results) >= limit:
                        return results
            except Exception:
                pass
    except Exception:
        pass
    return results


# ---------------------------------------------------------------------------
# Per-provider builders
# ---------------------------------------------------------------------------

def _build_spf_provider(name: str, spf_domain: str) -> list[dict]:
    print(f"  Querying SPF: {spf_domain} …", end=" ", flush=True)
    spf = _query_spf(spf_domain)
    if not spf:
        print("NOT FOUND")
        return []

    cidrs = _parse_ipv4_cidrs(spf)
    entries = []
    for cidr in cidrs:
        for ip in _sample_ips(cidr, n=3):
            entries.append({"ip": ip, "cidr": cidr, "source": f"{spf_domain} SPF"})

    print(f"{len(cidrs)} IPv4 CIDRs → {len(entries)} IPs")
    return entries


def _build_mx_provider(name: str, domain: str) -> list[dict]:
    print(f"  Resolving MX: {domain} …", end=" ", flush=True)
    pairs = _resolve_mx_ips(domain, limit=4)
    entries = [{"ip": ip, "cidr": None, "source": f"{host} (MX of {domain})"} for ip, host in pairs]
    print(f"{len(entries)} IPs")
    return entries


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------

_HEADER = '''\
"""
IP address table for DMARC sample data generation.

AUTO-GENERATED by tests/build_ip_table.py — do not edit by hand.
Regenerate when provider IP ranges change (run quarterly or when enrichment stops matching):

    python tests/build_ip_table.py

IPv4 only. IPv6 is intentionally excluded: see docs/developer-guide.md for the
known limitation around IPv6 geo-enrichment coverage in GeoLite2-City.

Generated: {ts}
"""
from __future__ import annotations

# Each entry: {{"ip": str, "cidr": str | None, "source": str}}
# geo_anomaly entries also include: "country", "country_name", "asn", "note"

PROVIDER_IPS: dict[str, list[dict]] = {data}
'''


def _render_entry(e: dict) -> str:
    parts = [f'"ip": "{e["ip"]}"']
    if "cidr" in e:
        parts.append(f'"cidr": {repr(e["cidr"])}')
    if "source" in e:
        parts.append(f'"source": {repr(e["source"])}')
    for k in ("country", "country_name", "asn", "note"):
        if k in e:
            parts.append(f'"{k}": {repr(e[k])}')
    return "{" + ", ".join(parts) + "}"


def _write_table(providers: dict[str, list[dict]], out_path: Path) -> None:
    lines = ["{\n"]
    for pname, entries in providers.items():
        lines.append(f'    "{pname}": [\n')
        for e in entries:
            lines.append(f"        {_render_entry(e)},\n")
        lines.append("    ],\n")
    lines.append("}")
    data = "".join(lines)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = _HEADER.format(ts=ts, data=data)
    out_path.write_text(content)
    print(f"\nWrote {out_path.resolve()}  ({out_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

ALL_PROVIDERS = list(SPF_SOURCES) + list(MX_SOURCES) + ["proofpoint", "geo_anomaly"]


def main():
    parser = argparse.ArgumentParser(description="Refresh tests/ip_table.py from live DNS")
    parser.add_argument("--dry-run", action="store_true", help="Print table without writing")
    parser.add_argument(
        "--provider", choices=ALL_PROVIDERS,
        help="Refresh only one provider (merges into existing ip_table.py)",
    )
    args = parser.parse_args()

    out_path = Path(__file__).parent / "ip_table.py"

    # Load existing table if doing a partial refresh
    existing: dict[str, list[dict]] = {}
    if args.provider and out_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location("ip_table", out_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        existing = dict(mod.PROVIDER_IPS)

    providers: dict[str, list[dict]] = {}

    def _should_build(name: str) -> bool:
        return args.provider is None or args.provider == name

    print("\nBuilding IP table from live DNS…\n")

    for name, spf_domain in SPF_SOURCES.items():
        if _should_build(name):
            providers[name] = _build_spf_provider(name, spf_domain)
        else:
            providers[name] = existing.get(name, [])

    for name, domain in MX_SOURCES.items():
        if _should_build(name):
            providers[name] = _build_mx_provider(name, domain)
        else:
            providers[name] = existing.get(name, [])

    if _should_build("proofpoint"):
        print(f"  Proofpoint: using manual entries ({len(PROOFPOINT_MANUAL)} IPs)")
        providers["proofpoint"] = PROOFPOINT_MANUAL
    else:
        providers["proofpoint"] = existing.get("proofpoint", PROOFPOINT_MANUAL)

    if _should_build("geo_anomaly"):
        print(f"  Geo-anomaly: {len(GEO_ANOMALY_IPS)} hardcoded IPs "
              f"({', '.join(e['country'] for e in GEO_ANOMALY_IPS)})")
        providers["geo_anomaly"] = GEO_ANOMALY_IPS
    else:
        providers["geo_anomaly"] = existing.get("geo_anomaly", GEO_ANOMALY_IPS)

    # Summary
    print("\nTable summary:")
    for name, entries in providers.items():
        print(f"  {name:<20} {len(entries):>3} entries")

    if args.dry_run:
        print("\n--dry-run: not writing ip_table.py")
        return

    _write_table(providers, out_path)


if __name__ == "__main__":
    main()