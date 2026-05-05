from sqlalchemy import func
from sqlalchemy.orm import Session
from core.models import Record
from intelligence.rules.base import BaseRule, FlagResult


class NewSenderIPRule(BaseRule):
    """Flag an IP that has never been seen before for this domain."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        domain = record.report.domain if record.report else None
        if not domain:
            return []

        prior_count = (
            db.query(func.count(Record.id))
            .join(Record.report)
            .filter(
                Record.source_ip == record.source_ip,
                Record.id != record.id,
            )
            .scalar()
        )

        if prior_count == 0:
            return [FlagResult(
                flag_type="new_sender_ip",
                severity="low",
                detail={"source_ip": record.source_ip, "domain": domain},
            )]
        return []