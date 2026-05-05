import logging
from sqlalchemy.orm import Session
from core.models import Report, Record, Flag
from intelligence.rules.auth import AuthFailureRule, PolicyMismatchRule, ForwardingPatternRule
from intelligence.rules.senders import NewSenderIPRule
from intelligence.rules.volume import VolumeSpikeRule
from intelligence.rules.geo import GeoAnomalyRule

log = logging.getLogger(__name__)

RULES = [
    AuthFailureRule(),
    PolicyMismatchRule(),
    ForwardingPatternRule(),
    NewSenderIPRule(),
    VolumeSpikeRule(),
    GeoAnomalyRule(),
]


def run_intelligence(db: Session, report: Report) -> int:
    total_flags = 0
    for record in report.records:
        for rule in RULES:
            try:
                results = rule.evaluate(record, db)
            except Exception as exc:
                log.error("Rule %s failed on record %d: %s", rule.__class__.__name__, record.id, exc)
                continue

            for result in results:
                db.add(Flag(
                    record_id=record.id,
                    client_id=record.client_id,
                    flag_type=result.flag_type,
                    severity=result.severity,
                    detail=result.detail,
                ))
                total_flags += 1

    if total_flags:
        db.commit()
        log.info("Report %d: %d intelligence flag(s) created", report.id, total_flags)
    return total_flags