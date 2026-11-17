"""Tests for exit interview Phase 3: Rectification."""


import pytest

from organvm_engine.governance.exit_interview.rectification import (
    rectify_module,
)
from organvm_engine.governance.exit_interview.schemas import (
    AxiomClaim,
    CounterTestimony,
    DimensionVerdict,
    Testimony,
    Verdict,
)


@pytest.fixture
def aligned_pair():
    """A testimony/counter pair that should mostly align."""
    testimony = Testimony(
        v1_path="meta-organvm/organvm-engine/governance",
        v2_mechanism="nervous",
        v2_verb="govern",
        feeds_gates=["nervous--govern/G1", "nervous--govern/G3"],
        existence={"score": 1.0, "evidence": "350 lines, 5 classes"},
        identity="Promotion state machine for governance lifecycle transitions",
        structure="5 classes, 12 functions; state_machine.py, audit.py, rules.py",
        law="Enforces governance-rules.json constraints; validates transitions",
        process="CLI entry: organvm governance promote",
        relation="imports from: registry, rules. imported by: audit, impact",
        teleology="Serves A6 (Organizational Closure)",
        signals_consumes=["STATE", "RULE"],
        signals_produces=["VALIDATION", "STATE", "CONSTRAINT"],
        axiom_alignment=[
            AxiomClaim(axiom="A6", claim="governance governs itself"),
        ],
    )
    counter = CounterTestimony(
        v1_path="meta-organvm/organvm-engine/governance",
        v2_mechanism="nervous",
        v2_verb="govern",
        gate_source="nervous--govern.yaml",
        existence={"required": True, "expected_lines": 10500},
        identity="governance — promotion state machine, dependency validation, audit",
        structure="Expected modules: governance/, coordination/",
        law="[G1] conductor imports from engine governance; [G3] tests pass",
        process="Required checks: ISOTOPES_RESOLVED, SIGNAL_DECLARED, TESTS_PASS",
        relation="Expected as source for nervous--govern",
        teleology="Serves A5, A2",
        expected_consumes=["TRACE", "REPORT", "STATE", "VALIDATION"],
        expected_produces=["RULE", "STATE", "VALIDATION", "CONSTRAINT"],
        defects_flagged=["conductor isotope", "V1 organ structure assumptions"],
        gates_served=["nervous--govern/G1", "nervous--govern/G2", "nervous--govern/G3"],
    )
    return testimony, counter


@pytest.fixture
def workspace_root(engine_workspace):
    """Temp workspace whose engine repo is the checkout under test."""
    return engine_workspace


class TestRectifyModule:
    def test_returns_eight_verdicts(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        assert len(verdicts) == 8  # 7 dimensions + signals
        assert all(isinstance(v, DimensionVerdict) for v in verdicts)

    def test_existence_aligns_when_file_exists(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        existence = next(v for v in verdicts if v.dimension == "existence")
        assert existence.verdict == Verdict.ALIGNED

    def test_identity_aligns_with_keyword_overlap(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        identity = next(v for v in verdicts if v.dimension == "identity")
        # Both mention "state machine" and "governance" → should align
        assert identity.verdict == Verdict.ALIGNED

    def test_all_verdicts_have_v1_and_v2(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        for v in verdicts:
            assert v.v1_says  # V1 testimony should be non-empty
            assert v.v2_says  # V2 counter should be non-empty

    def test_signals_detect_overlap(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        signals = next(v for v in verdicts if v.dimension == "signals")
        # STATE, VALIDATION overlap in both consumes/produces
        assert signals.verdict in (Verdict.ALIGNED, Verdict.CONTRADICTED, Verdict.V2_UNDERSPECS)


class TestVerdictEnum:
    def test_all_verdicts_have_string_values(self):
        for v in Verdict:
            assert isinstance(v.value, str)
            assert v.value == v.name

    def test_six_verdict_types(self):
        assert len(Verdict) == 6


class TestDimensionVerdictSerialization:
    def test_to_dict(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        for v in verdicts:
            d = v.to_dict()
            assert "dimension" in d
            assert "verdict" in d
            assert d["verdict"] in [vv.value for vv in Verdict]

    def test_remediation_only_when_present(self, aligned_pair, workspace_root):
        testimony, counter = aligned_pair
        verdicts = rectify_module(testimony, counter, workspace_root)
        for v in verdicts:
            d = v.to_dict()
            if v.remediation:
                assert "remediation" in d
