from ingestion.parser import parse_dmarc_xml

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8" ?>
<feedback>
  <report_metadata>
    <org_name>Google Inc.</org_name>
    <email>noreply-dmarc-support@google.com</email>
    <report_id>12345678901234567890</report_id>
    <date_range>
      <begin>1714521600</begin>
      <end>1714607999</end>
    </date_range>
  </report_metadata>
  <policy_published>
    <domain>example.com</domain>
    <adkim>r</adkim>
    <aspf>r</aspf>
    <p>quarantine</p>
    <sp>none</sp>
    <pct>100</pct>
  </policy_published>
  <record>
    <row>
      <source_ip>192.0.2.1</source_ip>
      <count>42</count>
      <policy_evaluated>
        <disposition>none</disposition>
        <dkim>pass</dkim>
        <spf>fail</spf>
      </policy_evaluated>
    </row>
    <identifiers>
      <header_from>example.com</header_from>
      <envelope_from>mail.example.com</envelope_from>
    </identifiers>
    <auth_results>
      <dkim>
        <domain>example.com</domain>
        <selector>default</selector>
        <result>pass</result>
      </dkim>
      <spf>
        <domain>mail.example.com</domain>
        <result>fail</result>
      </spf>
    </auth_results>
  </record>
</feedback>"""


def test_parse_report_metadata():
    report = parse_dmarc_xml(SAMPLE_XML)
    assert report.org_name == "Google Inc."
    assert report.report_id == "12345678901234567890"
    assert report.policy.domain == "example.com"
    assert report.policy.p == "quarantine"


def test_parse_records():
    report = parse_dmarc_xml(SAMPLE_XML)
    assert len(report.records) == 1
    rec = report.records[0]
    assert rec.source_ip == "192.0.2.1"
    assert rec.count == 42
    assert rec.dkim_result == "pass"
    assert rec.spf_result == "fail"
    assert rec.header_from == "example.com"


def test_parse_auth_results():
    report = parse_dmarc_xml(SAMPLE_XML)
    rec = report.records[0]
    assert len(rec.auth_results) == 2
    dkim = next(a for a in rec.auth_results if a.auth_type == "dkim")
    spf = next(a for a in rec.auth_results if a.auth_type == "spf")
    assert dkim.result == "pass"
    assert dkim.selector == "default"
    assert spf.result == "fail"