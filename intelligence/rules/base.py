from abc import ABC, abstractmethod
from dataclasses import dataclass
from core.models import Record
from sqlalchemy.orm import Session


@dataclass
class FlagResult:
    flag_type: str
    severity: str   # critical | high | medium | low | info
    detail: dict


class BaseRule(ABC):
    """All intelligence rules implement this interface."""

    @abstractmethod
    def evaluate(self, record: Record, db: Session) -> list[FlagResult]:
        """Return zero or more flags for the given record."""
        ...