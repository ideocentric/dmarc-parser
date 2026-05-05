from sqlalchemy import func
from sqlalchemy.orm import Session
from core.models import Record
from intelligence.rules.base import BaseRule, FlagResult

# Spike threshold: flag if current count exceeds N times the rolling average
SPIKE_MULTIPLIER = 5
# Minimum average to avoid false positives on low-volume senders
MIN_AVERAGE_COUNT = 10


class VolumeSpikeRule(BaseRule):
    """Flag a record whose message count is significantly above the historical average for that IP."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        avg = (
            db.query(func.avg(Record.count))
            .filter(
                Record.source_ip == record.source_ip,
                Record.id != record.id,
            )
            .scalar()
        )

        if avg is None or avg < MIN_AVERAGE_COUNT:
            return []

        if record.count >= avg * SPIKE_MULTIPLIER:
            return [FlagResult(
                flag_type="volume_spike",
                severity="medium",
                detail={
                    "source_ip": record.source_ip,
                    "current_count": record.count,
                    "historical_average": round(float(avg), 1),
                    "multiplier": round(record.count / float(avg), 1),
                },
            )]
        return []