from sqlalchemy.orm import Session
from core.models import Record
from intelligence.rules.base import BaseRule, FlagResult

FAIL_RESULTS = {"fail", "softfail", "permerror", "temperror"}


class AuthFailureRule(BaseRule):
    """Flag records where SPF or DKIM evaluation failed."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        flags: list[FlagResult] = []
        spf_fail = record.spf_result.lower() in FAIL_RESULTS
        dkim_fail = record.dkim_result.lower() in FAIL_RESULTS

        if spf_fail and dkim_fail:
            flags.append(FlagResult(
                flag_type="dkim_spf_both_fail",
                severity="critical",
                detail={"spf": record.spf_result, "dkim": record.dkim_result},
            ))
        elif spf_fail:
            flags.append(FlagResult(
                flag_type="spf_fail",
                severity="high",
                detail={"spf": record.spf_result},
            ))
        elif dkim_fail:
            flags.append(FlagResult(
                flag_type="dkim_fail",
                severity="high",
                detail={"dkim": record.dkim_result},
            ))
        return flags


class PolicyMismatchRule(BaseRule):
    """Flag when disposition is 'none' but published policy is quarantine or reject."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        report = record.report
        if not report:
            return []
        published_policy = (report.policy_p or "").lower()
        disposition = record.disposition.lower()
        if published_policy in {"quarantine", "reject"} and disposition == "none":
            return [FlagResult(
                flag_type="policy_mismatch",
                severity="medium",
                detail={"published_policy": published_policy, "disposition": disposition},
            )]
        return []


class ForwardingPatternRule(BaseRule):
    """SPF fail + DKIM pass is a classic email forwarding signature."""

    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        spf_fail = record.spf_result.lower() in FAIL_RESULTS
        dkim_pass = record.dkim_result.lower() == "pass"
        if spf_fail and dkim_pass:
            return [FlagResult(
                flag_type="forwarding_pattern",
                severity="info",
                detail={"spf": record.spf_result, "dkim": record.dkim_result},
            )]
        return []