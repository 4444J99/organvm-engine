"""Track promotion obligations and system-wide health metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ObligationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DISCHARGED = "discharged"
    OVERDUE = "overdue"


@dataclass
class PromotionObligation:
    """A pending obligation from the promotion state machine."""

    source_organ: str
    target_organ: str
    obligation_type: str
    description: str
    created_date: date
    status: ObligationStatus = ObligationStatus.PENDING
    due_date: date | None = None
    discharged_date: date | None = None

    @property
    def is_overdue(self) -> bool:
        if self.due_date and self.status == ObligationStatus.PENDING:
            return date.today() > self.due_date
        return False

    def discharge(self) -> None:
        self.status = ObligationStatus.DISCHARGED
        self.discharged_date = date.today()


@dataclass
class ObligationTracker:
    """Track all promotion obligations across the system."""

    obligations: list[PromotionObligation] = field(default_factory=list)

    def add(self, obligation: PromotionObligation) -> None:
        self.obligations.append(obligation)

    @property
    def pending(self) -> list[PromotionObligation]:
        return [o for o in self.obligations if o.status == ObligationStatus.PENDING]

    @property
    def discharged(self) -> list[PromotionObligation]:
        return [o for o in self.obligations if o.status == ObligationStatus.DISCHARGED]

    @property
    def overdue(self) -> list[PromotionObligation]:
        return [o for o in self.obligations if o.is_overdue]

    def by_organ(self, organ: str) -> list[PromotionObligation]:
        return [o for o in self.obligations if o.source_organ == organ or o.target_organ == organ]

    def summary(self) -> dict:
        return {
            "total": len(self.obligations),
            "pending": len(self.pending),
            "discharged": len(self.discharged),
            "overdue": len(self.overdue),
        }
