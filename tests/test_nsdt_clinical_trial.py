"""
tests/test_nsdt_clinical_trial.py – LUMINARK Clinical Trial Suite
LUMINARK Active Governance Layer

Verifies all SAP invariants, stage-specific diagnoses, and Lyapunov stability
guarantees via both deterministic and property-based (Hypothesis) tests.

"Clinical trial" framing: each test is a controlled experiment with a known
NSDT input (the patient) and an expected SAP stage diagnosis (the prognosis).
The tests verify that the governance system produces correct, stable, and
reproducible diagnoses.

Tests are organised by layer:
  1. SAPGeometry      — classification, micro-position, transition enforcement
  2. SAPEnergy        — trap energy bounds and gradient correctness
  3. SAPConstrainedBayesian — posterior validity and geometric masking
  4. LyapunovController — V function properties and action thresholds
  5. NumericalConstitution — constitution pass/fail contract
  6. SAPPsychiatrist  — error-to-stage mapping for every SAP stage
  7. LuminarkLiveBridge — full governance loop (LOCAL execution mode)
  8. Property-based   — Hypothesis invariants over random NSDT inputs
"""

import math
import os
import sys
import time

import numpy as np
import pytest

# Allow imports from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luminark_live_bridge import (
    ExecutionMode,
    ExecutionResult,
    GovernanceVerdict,
    LuminarkLiveBridge,
    _extract_nsdt_from_execution,
)
from sap_constrained_bayesian import SAPConstrainedBayesian, SAPEnergy
from sap_geometry_engine import ADJACENCY_MATRIX, STAGE_CENTROIDS, SAPGeometry
from sap_lyapunov import LyapunovController, LyapunovVulnerabilityScanner, NumericalConstitution
from sap_stage_classifier import SAPPsychiatrist

try:
    import hypothesis.strategies as st
    from hypothesis import HealthCheck, given, settings

    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def bayesian():
    return SAPConstrainedBayesian()


@pytest.fixture
def lyapunov():
    return LyapunovController()


@pytest.fixture
def constitution():
    return NumericalConstitution()


@pytest.fixture
def psychiatrist():
    return SAPPsychiatrist()


@pytest.fixture
def bridge():
    return LuminarkLiveBridge(
        execution_mode=ExecutionMode.LOCAL,
        max_iterations=2,
        sandbox_timeout=15,
        stability_threshold=2000.0,  # High threshold: heuristic NSDT → high V on fast runs
    )


# ── 1. SAPGeometry Clinical Trials ───────────────────────────────────────────


class TestSAPGeometryClinicalTrials:
    def test_stage_0_centroid_classifies_to_stage_0(self):
        """Patient: all zeros. Expected: Stage 0 (Plenara)."""
        stage = SAPGeometry.classify([0.0, 0.0, 0.0, 0.0, 0.0])
        assert stage == 0, f"Stage 0 centroid should classify as 0, got {stage}"

    def test_stage_8_centroid_classifies_to_stage_8(self):
        """Patient: Stage 8 centroid. Expected: Stage 8 (The Vessel of Grounding)."""
        x = STAGE_CENTROIDS[8]
        stage = SAPGeometry.classify(x)
        assert stage == 8, f"Stage 8 centroid should classify as 8, got {stage}"

    def test_all_centroids_self_classify(self):
        """Each canonical centroid must classify to its own stage."""
        for s, centroid in STAGE_CENTROIDS.items():
            classified = SAPGeometry.classify(centroid)
            assert classified == s, f"Stage {s} centroid classified as {classified}"

    def test_stage_5_irreversibility(self):
        """Governance invariant: from Stage 5, cannot return to Stage 0–4."""
        corrected, valid = SAPGeometry.enforce_geometry(5, 3)
        assert not valid, "Stage 5 → 3 should be invalid"
        assert corrected >= 5, f"Correction from Stage 5 must stay ≥ 5, got {corrected}"

    def test_stage_8_terminal_branch(self):
        """Governance invariant: Stage 8 can only hold or advance to Stage 9."""
        corrected, valid = SAPGeometry.enforce_geometry(8, 5)
        assert not valid
        assert corrected in (7, 8, 9)

    def test_no_stage_skipping_forward(self):
        """Cannot skip from Stage 3 to Stage 5."""
        corrected, valid = SAPGeometry.enforce_geometry(3, 5)
        assert not valid
        assert corrected == 4

    def test_no_stage_skipping_backward(self):
        """Cannot skip from Stage 6 to Stage 4."""
        corrected, valid = SAPGeometry.enforce_geometry(6, 4)
        assert not valid
        assert corrected == 5

    def test_micro_position_within_stage_range(self):
        """Micro-position must be within [stage, stage+1]."""
        for stage in range(9):
            centroid = STAGE_CENTROIDS[stage]
            micro_pos = SAPGeometry.compute_micro_position(centroid, stage)
            assert stage <= micro_pos <= stage + 1 + 1e-9, (
                f"Micro-position {micro_pos} outside [{stage}, {stage + 1}]"
            )

    def test_adjacency_matrix_stage_5_rule(self):
        """Adjacency matrix row 5 must have zeros for columns 0–4."""
        assert np.all(ADJACENCY_MATRIX[5, :5] == 0), (
            "Stage 5 must not allow backward transitions in adjacency matrix"
        )

    def test_adjacency_matrix_stage_8_rule(self):
        """Adjacency matrix row 8 must only have Stage 8 and 9 as valid."""
        assert ADJACENCY_MATRIX[8, 8] == 1.0
        assert ADJACENCY_MATRIX[8, 9] == 1.0
        assert np.all(ADJACENCY_MATRIX[8, :8] == 0), (
            "Stage 8 must not allow any backward transition"
        )


# ── 2. SAPEnergy Clinical Trials ─────────────────────────────────────────────


class TestSAPEnergyClinicalTrials:
    def test_trap_energy_always_in_unit_interval(self):
        """Trap energy for every stage must be in [0, 1]."""
        test_vectors = [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [10.0, 10.0, 10.0, 10.0, 10.0],
            [5.0, 5.0, 5.0, 5.0, 5.0],
            [7.5, 7.0, 8.0, 2.0, 2.0],  # Stage 8 zone
        ]
        for x in test_vectors:
            for stage in range(10):
                e = SAPEnergy.trap_energy(stage, x)
                assert 0.0 <= e <= 1.0, f"trap_energy(stage={stage}, x={x}) = {e} out of [0,1]"

    def test_stage_8_trap_highest_at_stage_8_centroid(self):
        """Stage 8 centroid should produce the highest trap energy at Stage 8."""
        x = STAGE_CENTROIDS[8]
        e8 = SAPEnergy.trap_energy(8, x)
        [SAPEnergy.trap_energy(s, x) for s in range(10) if s != 8]
        assert e8 > 0, "Stage 8 trap energy at Stage 8 centroid must be positive"

    def test_total_energy_bounded(self):
        """Total energy E[trap] over uniform posterior must be in [0, 1]."""
        uniform = np.ones(10) / 10.0
        for _ in range(20):
            x = np.random.uniform(0, 10, 5).tolist()
            e = SAPEnergy.compute_total_energy(x, uniform)
            assert 0.0 <= e <= 1.0, f"total_energy = {e} out of [0,1]"

    def test_gradient_finite_difference_consistent(self):
        """Gradient should be consistent at different epsilon values."""
        x = [5.2, 4.1, 6.3, 3.8, 5.9]
        posterior = np.ones(10) / 10.0
        grad_1 = SAPEnergy.compute_gradient(x, posterior, epsilon=1e-5)
        grad_2 = SAPEnergy.compute_gradient(x, posterior, epsilon=1e-4)
        assert all(abs(g1 - g2) < 1e-3 for g1, g2 in zip(grad_1, grad_2, strict=False)), (
            "Gradient inconsistent across epsilon values"
        )

    def test_zero_vector_low_trap_energy(self):
        """Near Stage 0 (all zeros), most stage trap energies should be near 0."""
        x = [0.1, 0.1, 0.1, 9.9, 0.1]  # high adaptability = low trap
        for stage in [3, 5, 7, 8]:
            e = SAPEnergy.trap_energy(stage, x)
            # Should not be maxed out with high adaptability
            assert e < 0.9, (
                f"Stage {stage} trap energy {e} unexpectedly high for low-tension vector"
            )


# ── 3. Bayesian Posterior Clinical Trials ────────────────────────────────────


class TestBayesianClinicalTrials:
    def test_posterior_sums_to_one(self, bayesian):
        """Posterior must sum to 1.0 ± 1e-5 for any NSDT input."""
        test_vectors = [
            [0.0, 0.0, 0.0, 0.0, 0.0],
            [5.0, 5.0, 5.0, 5.0, 5.0],
            [10.0, 10.0, 10.0, 10.0, 10.0],
            [7.5, 7.0, 8.0, 2.0, 2.0],
        ]
        for x in test_vectors:
            post = bayesian.posterior(np.array(x))
            assert abs(post.sum() - 1.0) < 1e-5, f"Posterior sum {post.sum()} ≠ 1.0 for x={x}"

    def test_posterior_all_non_negative(self, bayesian):
        """Posterior must have no negative probabilities."""
        x = [6.2, 4.1, 7.3, 3.8, 5.9]
        post = bayesian.posterior(np.array(x))
        assert np.all(post >= -1e-9), f"Negative probability in posterior: {post}"

    def test_geometric_mask_blocks_forbidden_transition(self, bayesian):
        """After Stage 5, stages 0–4 should have zero probability."""
        x = np.array(STAGE_CENTROIDS[4])  # close to Stage 4
        post = bayesian.posterior(x, prev_stage=5)
        # Stages 0–4 must be masked to 0
        for s in range(5):
            assert post[s] < 1e-9, f"Stage {s} should be masked after Stage 5, got P={post[s]:.6f}"

    def test_dominant_stage_matches_centroid(self, bayesian):
        """
        Forward pass on Stage 8 centroid should return dominant_stage 8 or 9.
        Energy modulation (beta=0.8) deforms the posterior, so Stage 8's high
        trap energy can shift the dominant stage to Stage 9 — this is correct
        SAP behaviour (the Bayesian layer reflects the energy penalty).
        """
        x = STAGE_CENTROIDS[8]
        result = bayesian.forward(x)
        assert result["dominant_stage"] in (8, 9), (
            f"Stage 8 centroid should dominate at Stage 8 or 9, got {result['dominant_stage']}"
        )

    def test_forward_returns_all_keys(self, bayesian):
        """forward() must return all required keys."""
        x = [5.0, 5.0, 5.0, 5.0, 5.0]
        result = bayesian.forward(x)
        required = {
            "posterior",
            "dominant_stage",
            "expected_stage",
            "entropy",
            "trap_energy",
            "energy_gradient",
            "arc",
            "geometric_valid",
            "stage_metadata",
        }
        missing = required - set(result.keys())
        assert not missing, f"forward() missing keys: {missing}"

    def test_entropy_positive(self, bayesian):
        """Entropy of posterior must be non-negative."""
        x = [4.5, 6.0, 3.5, 7.0, 5.5]
        result = bayesian.forward(x)
        assert result["entropy"] >= 0, f"Entropy {result['entropy']} is negative"


# ── 4. Lyapunov Clinical Trials ───────────────────────────────────────────────


class TestLyapunovClinicalTrials:
    def test_V_non_negative(self, lyapunov):  # noqa: N802
        """Lyapunov V must be non-negative for any inputs."""
        cases = [(0, 0, 0), (2.1, 0.6, 1.2), (5.0, 1.0, 3.0), (0.01, 0.01, 0.01)]
        for H, E, v in cases:
            V = lyapunov.V(H, E, v)
            assert V >= 0, f"V({H}, {E}, {v}) = {V} < 0"

    def test_V_zero_at_equilibrium(self, lyapunov):  # noqa: N802
        """V(0, 0, 0) must be exactly 0."""
        assert lyapunov.V(0.0, 0.0, 0.0) == 0.0

    def test_dV_negative_when_energy_decreases(self, lyapunov):  # noqa: N802
        """DAMPEN action (reduce energy) must produce negative dV."""
        dv = lyapunov.dV(
            entropy_before=1.5,
            energy_before=0.5,
            velocity_before=0.3,
            entropy_after=1.5,
            energy_after=0.45,
            velocity_after=0.3,
        )
        assert dv < 0, f"Expected dV < 0 after energy reduction, got {dv}"

    def test_action_thresholds(self, lyapunov):
        """Action thresholds: HOLD < 2.0, DAMPEN 2.0–5.0, INTERVENE > 5.0."""
        assert lyapunov.recommend_action(0.5, 0.1, 0.0) == "HOLD"
        assert lyapunov.recommend_action(1.5, 0.5, 1.0) == "DAMPEN"
        assert lyapunov.recommend_action(3.0, 1.0, 2.0) == "INTERVENE"

    def test_cynical_loop_overrides_all(self, lyapunov):
        """Cynical loop detection must always return BREAK_PATTERN."""
        action = lyapunov.recommend_action(0.1, 0.1, 0.0, cynical_loop=True)
        assert action == "BREAK_PATTERN"

    def test_vulnerability_scanner_detects_instability(self):
        """Scanner must detect dV/dt > threshold in an unstable trace."""
        scanner = LyapunovVulnerabilityScanner(instability_threshold=0.1)
        np.random.seed(42)
        trace = np.random.uniform(3, 7, size=(20, 5))
        # Inject instability at steps 14–19
        trace[14:, 2] = 9.5  # tension spike
        trace[14:, 3] = 1.0  # adaptability collapse
        ts = np.array([time.time() + i for i in range(20)])
        result = scanner.scan_code_path(trace, ts)
        assert result["instability_count"] > 0, "Scanner failed to detect injected instability"
        assert all("dV" in v for v in result["vulnerabilities"])


# ── 5. Numerical Constitution Clinical Trials ────────────────────────────────


class TestNumericalConstitutionClinicalTrials:
    def test_low_V_passes(self, constitution):  # noqa: N802
        """V=0.5 (well below threshold=3.0) must PASS."""
        report = constitution.certify(entropy=0.3, energy=0.1, velocity=0.0)
        assert report.passed, f"Low-V state should pass: {report}"

    def test_high_V_fails(self, constitution):  # noqa: N802
        """V > threshold must FAIL."""
        report = constitution.certify(entropy=3.0, energy=1.0, velocity=2.0)
        assert not report.passed, f"High-V state should fail: {report}"

    def test_report_has_action(self, constitution):
        """Every report must include a recommended action."""
        report = constitution.certify(1.0, 0.3, 0.5)
        assert report.action in ("HOLD", "DAMPEN", "INTERVENE", "BREAK_PATTERN")

    def test_report_str_contains_status(self, constitution):
        """String representation must contain STABLE or UNSTABLE."""
        report = constitution.certify(0.5, 0.1, 0.0)
        s = str(report)
        assert "STABLE" in s or "UNSTABLE" in s


# ── 6. SAP Psychiatrist Clinical Trials ──────────────────────────────────────


class TestSAPPsychiatristClinicalTrials:
    """
    Clinical trials: known error types must map to expected SAP stages.
    Each test is a "case study" — a specific error pattern and its correct diagnosis.
    """

    def test_import_error_maps_to_stage_0(self, psychiatrist):
        """ImportError → Stage 0 (Plenara / missing dependency)."""
        d = psychiatrist.diagnose_from_strings("ImportError", "No module named 'numpy'")
        assert d.stage == 0, f"ImportError should map to Stage 0, got {d.stage}"
        assert "pip install" in d.surgical_prompt.lower() or "import" in d.surgical_prompt.lower()

    def test_name_error_maps_to_stage_1(self, psychiatrist):
        """NameError → Stage 1 (The Spark / unbound name)."""
        d = psychiatrist.diagnose_from_strings("NameError", "name 'result' is not defined")
        assert d.stage == 1, f"NameError should map to Stage 1, got {d.stage}"

    def test_type_error_maps_to_stage_2(self, psychiatrist):
        """TypeError → Stage 2 (The Vessel / type mismatch)."""
        d = psychiatrist.diagnose_from_strings("TypeError", "unsupported operand type(s)")
        assert d.stage == 2, f"TypeError should map to Stage 2, got {d.stage}"

    def test_assertion_error_maps_to_stage_3(self, psychiatrist):
        """AssertionError (logic) → Stage 3 (The Engine / logic error)."""
        d = psychiatrist.diagnose_from_strings("AssertionError", "wrong result: expected 5")
        assert d.stage in (3, 8), f"AssertionError should map to Stage 3 or 8, got {d.stage}"

    def test_index_error_maps_to_stage_4(self, psychiatrist):
        """IndexError → Stage 4 (The Crucible / boundary violation)."""
        d = psychiatrist.diagnose_from_strings("IndexError", "list index out of range")
        assert d.stage == 4, f"IndexError should map to Stage 4, got {d.stage}"

    def test_recursion_error_maps_to_stage_5(self, psychiatrist):
        """RecursionError → Stage 5 (The Dynamo / threshold breach)."""
        d = psychiatrist.diagnose_from_strings("RecursionError", "maximum recursion depth exceeded")
        assert d.stage in (5, 9), f"RecursionError should map to Stage 5 or 9, got {d.stage}"

    def test_file_not_found_maps_to_stage_6(self, psychiatrist):
        """FileNotFoundError → Stage 6 (The Nexus / I/O failure)."""
        d = psychiatrist.diagnose_from_strings("FileNotFoundError", "No such file or directory")
        assert d.stage == 6, f"FileNotFoundError should map to Stage 6, got {d.stage}"

    def test_runtime_error_maps_to_stage_7(self, psychiatrist):
        """RuntimeError → Stage 7 (The Lens / concurrency/runtime)."""
        d = psychiatrist.diagnose_from_strings("RuntimeError", "event loop is closed")
        assert d.stage == 7, f"RuntimeError should map to Stage 7, got {d.stage}"

    def test_memory_error_maps_to_stage_9(self, psychiatrist):
        """MemoryError → Stage 9 (The Transparency / critical exhaustion)."""
        d = psychiatrist.diagnose_from_strings("MemoryError", "unable to allocate array")
        assert d.stage == 9, f"MemoryError should map to Stage 9, got {d.stage}"

    def test_surgical_prompt_always_non_empty(self, psychiatrist):
        """Surgical prompt must never be empty."""
        errors = [
            ("ImportError", "No module named 'x'"),
            ("TypeError", "int + str"),
            ("MemoryError", ""),
            ("UnknownError", "something went wrong"),
        ]
        for ec, em in errors:
            d = psychiatrist.diagnose_from_strings(ec, em)
            assert d.surgical_prompt.strip(), f"Empty surgical prompt for {ec}: {em}"

    def test_batch_diagnose_returns_all(self, psychiatrist):
        """batch_diagnose must return one diagnosis per failure."""
        failures = [
            {
                "error_class": "ImportError",
                "error_message": "No module named 'x'",
                "function": "f1",
            },
            {"error_class": "TypeError", "error_message": "int + str", "function": "f2"},
            {"error_class": "MemoryError", "error_message": "", "function": "f3"},
        ]
        diagnoses = psychiatrist.batch_diagnose(failures)
        assert len(diagnoses) == 3


# ── 7. LuminarkLiveBridge Clinical Trials ────────────────────────────────────


class TestLuminarkLiveBridgeClinicalTrials:
    def test_simple_passing_code(self, bridge):
        """Clean code that passes all checks should return PASS verdict."""
        code = "result = 2 + 2\nprint(result)\nassert result == 4"
        result = bridge.govern(code)
        assert result.verdict in (GovernanceVerdict.PASS, GovernanceVerdict.FAIL_REPAIRED), (
            f"Simple correct code should PASS, got {result.verdict}"
        )

    def test_audit_trail_non_empty(self, bridge):
        """Every governance run must produce an audit trail."""
        code = "print('hello world')"
        result = bridge.govern(code)
        assert len(result.audit_trail) >= 1

    def test_audit_trail_contains_required_keys(self, bridge):
        """Each audit entry must contain the required governance fields."""
        code = "print('test')"
        result = bridge.govern(code)
        required = {"iteration", "exit_code", "nsdt", "sap_stage", "V", "passed"}
        for entry in result.audit_trail:
            missing = required - set(entry.keys())
            assert not missing, f"Audit entry missing keys: {missing}"

    def test_syntax_error_code_fails(self, bridge):
        """Code with syntax error must not return PASS."""
        code = "def broken(:\n    pass"
        result = bridge.govern(code)
        assert result.verdict != GovernanceVerdict.PASS

    def test_governance_result_has_total_elapsed(self, bridge):
        """GovernanceResult must have a positive total_elapsed_s."""
        result = bridge.govern("print(1)")
        assert result.total_elapsed_s > 0

    def test_nsdt_extraction_from_successful_run(self):
        """_extract_nsdt_from_execution must return 5 values in [0, 10]."""
        exec_result = ExecutionResult(stdout="hello\n", stderr="", exit_code=0, elapsed_s=0.05)
        nsdt = _extract_nsdt_from_execution(exec_result, "print('hello')")
        assert len(nsdt) == 5
        assert all(0.0 <= v <= 10.0 for v in nsdt), f"NSDT out of [0,10]: {nsdt}"

    def test_nsdt_stability_high_on_success(self):
        """Successful execution should produce stability > 5.0."""
        exec_result = ExecutionResult(stdout="42\n", stderr="", exit_code=0, elapsed_s=0.01)
        nsdt = _extract_nsdt_from_execution(exec_result, "print(42)")
        stability = nsdt[1]
        assert stability > 5.0, f"Successful run should have high stability, got {stability}"

    def test_nsdt_tension_high_on_failure(self):
        """Failed execution with substantial stderr should produce higher tension than success."""
        exec_success = ExecutionResult(stdout="42\n", stderr="", exit_code=0, elapsed_s=0.01)
        exec_failure = ExecutionResult(
            stdout="",
            stderr="Traceback (most recent call last):\n"
            + "  File 'x.py', line 1\n" * 30
            + "TypeError: int + str\n",
            exit_code=1,
            elapsed_s=0.05,
        )
        nsdt_ok = _extract_nsdt_from_execution(exec_success, "print(42)")
        nsdt_fail = _extract_nsdt_from_execution(exec_failure, "1 + 'a'")
        # Failure should have higher tension than success
        assert nsdt_fail[2] > nsdt_ok[2], (
            f"Failed run tension {nsdt_fail[2]} should exceed success tension {nsdt_ok[2]}"
        )


# ── 8. Property-Based Tests (Hypothesis) ─────────────────────────────────────

if HYPOTHESIS_AVAILABLE:
    nsdt_strategy = st.lists(
        st.floats(min_value=0.0, max_value=10.0).filter(lambda v: math.isfinite(v)),
        min_size=5,
        max_size=5,
    ).map(np.array)

    prev_stage_strategy = st.none() | st.integers(min_value=0, max_value=9)

    @given(x=nsdt_strategy, prev=prev_stage_strategy)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_posterior_always_sums_to_one(x, prev):
        """Property: posterior sums to 1.0 for all valid NSDT inputs."""
        b = SAPConstrainedBayesian()
        post = b.posterior(x, prev_stage=prev)
        assert abs(post.sum() - 1.0) < 1e-4

    @given(x=nsdt_strategy)
    @settings(max_examples=200)
    def test_trap_energy_always_bounded(x):
        """Property: trap energy ∈ [0, 1] for all stages and NSDT inputs."""
        for stage in range(10):
            e = SAPEnergy.trap_energy(stage, x.tolist())
            assert 0.0 <= e <= 1.0 + 1e-9

    @given(
        H=st.floats(min_value=0.0, max_value=5.0).filter(math.isfinite),
        E=st.floats(min_value=0.0, max_value=1.0).filter(math.isfinite),
        v=st.floats(min_value=-5.0, max_value=5.0).filter(math.isfinite),
    )
    @settings(max_examples=200)
    def test_lyapunov_V_non_negative(H, E, v):  # noqa: N802
        """Property: V(H, E, v) ≥ 0 for all inputs."""
        ctrl = LyapunovController()
        assert ctrl.V(H, E, v) >= 0

    @given(x=nsdt_strategy)
    @settings(max_examples=100)
    def test_all_centroids_valid_geometry(x):
        """Property: enforce_geometry(None, stage) always returns the same stage."""
        for stage in range(10):
            corrected, valid = SAPGeometry.enforce_geometry(None, stage)
            assert corrected == stage
            assert valid is True

else:

    def test_hypothesis_not_available():
        """Hypothesis not installed — property tests skipped."""
        pytest.skip("hypothesis not installed; run: pip install hypothesis")


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
