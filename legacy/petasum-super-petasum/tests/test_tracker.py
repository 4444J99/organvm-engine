"""Tests for the obligation tracker."""

from datetime import date, timedelta

from src.tracker import ObligationStatus, ObligationTracker, PromotionObligation


def _sample_obligation(**overrides) -> PromotionObligation:
    defaults = {
        "source_organ": "I",
        "target_organ": "II",
        "obligation_type": "repo_creation",
        "description": "Create art-from repo",
        "created_date": date.today(),
    }
    defaults.update(overrides)
    return PromotionObligation(**defaults)


class TestPromotionObligation:
    def test_default_status(self):
        ob = _sample_obligation()
        assert ob.status == ObligationStatus.PENDING

    def test_discharge(self):
        ob = _sample_obligation()
        ob.discharge()
        assert ob.status == ObligationStatus.DISCHARGED
        assert ob.discharged_date == date.today()

    def test_overdue(self):
        ob = _sample_obligation(due_date=date.today() - timedelta(days=1))
        assert ob.is_overdue is True

    def test_not_overdue(self):
        ob = _sample_obligation(due_date=date.today() + timedelta(days=1))
        assert ob.is_overdue is False

    def test_discharged_not_overdue(self):
        ob = _sample_obligation(due_date=date.today() - timedelta(days=1))
        ob.discharge()
        assert ob.is_overdue is False


class TestObligationTracker:
    def test_add_obligation(self):
        tracker = ObligationTracker()
        tracker.add(_sample_obligation())
        assert len(tracker.obligations) == 1

    def test_pending_filter(self):
        tracker = ObligationTracker()
        tracker.add(_sample_obligation())
        ob2 = _sample_obligation()
        ob2.discharge()
        tracker.add(ob2)
        assert len(tracker.pending) == 1

    def test_discharged_filter(self):
        tracker = ObligationTracker()
        ob = _sample_obligation()
        ob.discharge()
        tracker.add(ob)
        assert len(tracker.discharged) == 1

    def test_by_organ(self):
        tracker = ObligationTracker()
        tracker.add(_sample_obligation(source_organ="I"))
        tracker.add(_sample_obligation(source_organ="III"))
        assert len(tracker.by_organ("I")) == 1

    def test_summary(self):
        tracker = ObligationTracker()
        tracker.add(_sample_obligation())
        s = tracker.summary()
        assert s["total"] == 1
        assert s["pending"] == 1
