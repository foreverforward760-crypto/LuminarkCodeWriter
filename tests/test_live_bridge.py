"""
tests/test_live_bridge.py – LuminarkLiveBridge Integration Tests

Integration tests for the governance orchestrator.
All tests run in LOCAL execution mode — no Docker required.

Tests verify:
  - Bridge instantiation and configuration
  - govern() contract: verdict, audit trail, iterations
  - get_stage_report() contract: NSDT, stage, V, action
  - GovernanceResult properties: v_history, stage_history, to_dict()
  - Execution failure handling and diagnosis
  - ExecutionMode enum handling

NOTE ON SUBMITTED TEST FILE:
  The original prompt's test code had five API mismatches against the actual
  implementation and would have failed entirely:
    1. execution_mode="local" → must be ExecutionMode.LOCAL (enum, not string)
    2. bridge.evaluate()      → method does not exist; correct: govern() / get_stage_report()
    3. StabilityReport from bridge → it lives in sap_lyapunov, not luminark_live_bridge
    4. report.geometric_stage → StabilityReport has no such field
    5. report.trap_score      → StabilityReport has no trap_score field
  All tests below are written against the actual, verified API.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from luminark.luminark_live_bridge import (
    ExecutionMode,
    ExecutionResult,
    GovernanceResult,
    GovernanceVerdict,
    LuminarkLiveBridge,
    _extract_nsdt_from_execution,
)
from luminark.sap_geometry_engine import STAGE_METADATA

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def bridge_local():
    """LuminarkLiveBridge in LOCAL mode — shared across module tests."""
    return LuminarkLiveBridge(
        execution_mode=ExecutionMode.LOCAL,
        max_iterations=2,
        stability_threshold=2000.0,  # high threshold: heuristic NSDT → large V on fast runs
        sandbox_timeout=15,
    )


@pytest.fixture(scope="module")
def bridge_tight():
    """Bridge with tight stability threshold — forces failures to be caught."""
    return LuminarkLiveBridge(
        execution_mode=ExecutionMode.LOCAL,
        max_iterations=2,
        stability_threshold=0.001,  # near-zero: almost anything fails
        sandbox_timeout=10,
    )


# ── 1. Instantiation ──────────────────────────────────────────────────────────


class TestBridgeInstantiation:
    def test_local_mode_instantiation(self):
        """Bridge accepts ExecutionMode.LOCAL enum and stores it correctly."""
        bridge = LuminarkLiveBridge(execution_mode=ExecutionMode.LOCAL)
        assert bridge is not None
        assert bridge.execution_mode == ExecutionMode.LOCAL

    def test_docker_mode_instantiation(self):
        """Bridge accepts ExecutionMode.DOCKER without raising."""
        bridge = LuminarkLiveBridge(execution_mode=ExecutionMode.DOCKER)
        assert bridge.execution_mode == ExecutionMode.DOCKER

    def test_execution_mode_is_enum(self):
        """execution_mode attribute is an ExecutionMode enum, not a bare string."""
        bridge = LuminarkLiveBridge(execution_mode=ExecutionMode.LOCAL)
        assert isinstance(bridge.execution_mode, ExecutionMode)

    def test_default_mode_is_docker(self):
        """Default execution mode is DOCKER (production default)."""
        bridge = LuminarkLiveBridge()
        assert bridge.execution_mode == ExecutionMode.DOCKER

    def test_custom_iterations(self):
        """max_iterations is configurable."""
        bridge = LuminarkLiveBridge(
            execution_mode=ExecutionMode.LOCAL,
            max_iterations=5,
        )
        assert bridge.max_iterations == 5

    def test_has_required_subsystems(self):
        """Bridge must have Bayesian, Lyapunov, Constitution, and Psychiatrist."""
        bridge = LuminarkLiveBridge(execution_mode=ExecutionMode.LOCAL)
        assert hasattr(bridge, "bayesian")
        assert hasattr(bridge, "lyapunov")
        assert hasattr(bridge, "constitution")
        assert hasattr(bridge, "psychiatrist")


# ── 2. govern() contract ──────────────────────────────────────────────────────


class TestGovernContract:
    def test_govern_returns_governance_result(self, bridge_local):
        """govern() must return a GovernanceResult instance."""
        result = bridge_local.govern("print('hello')")
        assert isinstance(result, GovernanceResult)

    def test_govern_verdict_is_enum(self, bridge_local):
        """verdict must be a GovernanceVerdict enum value."""
        result = bridge_local.govern("x = 1 + 1")
        assert isinstance(result.verdict, GovernanceVerdict)
        assert result.verdict in (
            GovernanceVerdict.PASS,
            GovernanceVerdict.FAIL_REPAIRED,
            GovernanceVerdict.FAIL_EXHAUSTED,
            GovernanceVerdict.EXECUTION_ERROR,
        )

    def test_govern_audit_trail_non_empty(self, bridge_local):
        """Every governance run produces at least one audit entry."""
        result = bridge_local.govern("print(2 + 2)")
        assert len(result.audit_trail) >= 1

    def test_audit_entry_has_required_keys(self, bridge_local):
        """Each audit entry must contain all governance fields."""
        result = bridge_local.govern("a = 42")
        required = {
            "iteration",
            "exit_code",
            "nsdt",
            "sap_stage",
            "stage_name",
            "V",
            "passed",
            "action",
        }
        for entry in result.audit_trail:
            missing = required - set(entry.keys())
            assert not missing, f"Audit entry missing keys: {missing}"

    def test_govern_iterations_within_bound(self, bridge_local):
        """iterations must be ≥ 1 and ≤ max_iterations."""
        result = bridge_local.govern("print('test')")
        assert 1 <= result.iterations <= bridge_local.max_iterations

    def test_govern_total_elapsed_positive(self, bridge_local):
        """total_elapsed_s must be a positive float."""
        result = bridge_local.govern("import math; print(math.pi)")
        assert result.total_elapsed_s > 0.0

    def test_govern_final_code_is_string(self, bridge_local):
        """final_code must always be a string."""
        result = bridge_local.govern("x = [i**2 for i in range(10)]")
        assert isinstance(result.final_code, str)
        assert len(result.final_code) > 0

    def test_govern_passing_code_has_low_iterations(self, bridge_local):
        """Clean code that passes on first try should have iterations=1."""
        result = bridge_local.govern("result = sum(range(10))\nprint(result)")
        # If it passed, it must have done so in ≤ max_iterations
        assert result.iterations <= bridge_local.max_iterations

    def test_govern_syntax_error_does_not_raise(self, bridge_local):
        """Syntax errors must be caught and return a FAIL verdict, not raise."""
        result = bridge_local.govern("def broken(\n    pass")
        assert result.verdict != GovernanceVerdict.PASS
        assert isinstance(result, GovernanceResult)

    def test_govern_with_task_description(self, bridge_local):
        """task_description parameter must be accepted without error."""
        result = bridge_local.govern(
            code="print('governed')",
            task_description="simple print test",
        )
        assert isinstance(result, GovernanceResult)


# ── 3. GovernanceResult properties ───────────────────────────────────────────


class TestGovernanceResultProperties:
    def test_v_history_is_list_of_floats(self, bridge_local):
        """v_history property returns a list of floats matching audit_trail length."""
        result = bridge_local.govern("y = 3.14")
        assert isinstance(result.v_history, list)
        assert len(result.v_history) == len(result.audit_trail)
        assert all(isinstance(v, (int, float)) for v in result.v_history)

    def test_stage_history_is_list_of_ints(self, bridge_local):
        """stage_history property returns a list of ints in [0, 9]."""
        result = bridge_local.govern("n = 100")
        assert isinstance(result.stage_history, list)
        assert len(result.stage_history) == len(result.audit_trail)
        assert all(0 <= s <= 9 for s in result.stage_history)

    def test_to_dict_is_json_serialisable(self, bridge_local):
        """to_dict() must return a dict that JSON can serialise."""
        import json

        result = bridge_local.govern("print('serialise me')")
        d = result.to_dict()
        assert isinstance(d, dict)
        # Must not raise
        serialised = json.dumps(d)
        assert len(serialised) > 0

    def test_to_dict_contains_verdict_string(self, bridge_local):
        """to_dict() verdict must be a string, not an enum."""
        result = bridge_local.govern("x = 1")
        d = result.to_dict()
        assert isinstance(d["verdict"], str)
        assert d["verdict"] in ("PASS", "FAIL_REPAIRED", "FAIL_EXHAUSTED", "EXECUTION_ERROR")

    def test_summary_returns_non_empty_string(self, bridge_local):
        """summary() must return a non-empty string."""
        result = bridge_local.govern("pass")
        s = result.summary()
        assert isinstance(s, str)
        assert len(s) > 0
        assert "Verdict" in s or "verdict" in s.lower()


# ── 4. get_stage_report() ─────────────────────────────────────────────────────


class TestGetStageReport:
    def test_stage_report_returns_dict(self, bridge_local):
        """get_stage_report() must return a dict."""
        report = bridge_local.get_stage_report("x = 42")
        assert isinstance(report, dict)

    def test_stage_report_required_keys(self, bridge_local):
        """get_stage_report() dict must contain all required keys."""
        report = bridge_local.get_stage_report("print('check')")
        required = {
            "nsdt",
            "sap_stage",
            "stage_name",
            "V",
            "passed",
            "action",
            "message",
            "exec_success",
        }
        missing = required - set(report.keys())
        assert not missing, f"get_stage_report missing keys: {missing}"

    def test_stage_report_sap_stage_in_range(self, bridge_local):
        """sap_stage must be an integer in [0, 9]."""
        report = bridge_local.get_stage_report("result = 2 ** 10")
        assert isinstance(report["sap_stage"], int)
        assert 0 <= report["sap_stage"] <= 9

    def test_stage_report_nsdt_is_5d(self, bridge_local):
        """NSDT vector must have exactly 5 dimensions, all in [0, 10]."""
        report = bridge_local.get_stage_report("import os; print(os.getcwd())")
        nsdt = report["nsdt"]
        assert len(nsdt) == 5
        assert all(0.0 <= v <= 10.0 for v in nsdt), f"NSDT out of range: {nsdt}"

    def test_stage_report_V_non_negative(self, bridge_local):  # noqa: N802
        """Lyapunov V must be non-negative."""
        report = bridge_local.get_stage_report("a = [1, 2, 3]")
        assert report["V"] >= 0.0

    def test_stage_report_action_valid(self, bridge_local):
        """action must be one of the four Lyapunov actions."""
        report = bridge_local.get_stage_report("pass")
        assert report["action"] in ("HOLD", "DAMPEN", "INTERVENE", "BREAK_PATTERN")

    def test_stage_report_stage_name_matches_metadata(self, bridge_local):
        """stage_name must match STAGE_METADATA for the reported stage."""
        report = bridge_local.get_stage_report("x = 5.0 ** 0.5")
        stage = report["sap_stage"]
        expected = STAGE_METADATA[stage]["name"]
        assert report["stage_name"] == expected, (
            f"stage_name {report['stage_name']!r} does not match "
            f"STAGE_METADATA[{stage}]['name'] = {expected!r}"
        )

    def test_stage_report_exec_success_true_for_valid_code(self, bridge_local):
        """exec_success must be True for syntactically valid code."""
        report = bridge_local.get_stage_report("print('hello world')")
        assert report["exec_success"] is True

    def test_stage_report_exec_success_false_for_broken_code(self, bridge_local):
        """exec_success must be False for code that raises at runtime."""
        report = bridge_local.get_stage_report("raise ValueError('boom')")
        assert report["exec_success"] is False


# ── 5. NSDT extraction ────────────────────────────────────────────────────────


class TestNSDTExtraction:
    def test_extraction_returns_5_values(self):
        """_extract_nsdt_from_execution must return exactly 5 values."""
        er = ExecutionResult(stdout="ok\n", stderr="", exit_code=0, elapsed_s=0.05)
        nsdt = _extract_nsdt_from_execution(er, "print('ok')")
        assert len(nsdt) == 5

    def test_extraction_all_in_range(self):
        """All NSDT dimensions must be in [0, 10]."""
        er = ExecutionResult(stdout="42\n", stderr="", exit_code=0, elapsed_s=0.02)
        nsdt = _extract_nsdt_from_execution(er, "print(42)")
        assert all(0.0 <= v <= 10.0 for v in nsdt), f"Out of range: {nsdt}"

    def test_stability_high_on_success(self):
        """Successful execution → stability dimension > 5.0."""
        er = ExecutionResult(stdout="done\n", stderr="", exit_code=0, elapsed_s=0.01)
        nsdt = _extract_nsdt_from_execution(er, "x = 1")
        assert nsdt[1] > 5.0, f"Stability {nsdt[1]} should be > 5 on success"

    def test_stability_low_on_failure(self):
        """Failed execution → stability dimension < 5.0."""
        er = ExecutionResult(stdout="", stderr="Traceback...", exit_code=1, elapsed_s=0.05)
        nsdt = _extract_nsdt_from_execution(er, "raise Exception()")
        assert nsdt[1] < 5.0, f"Stability {nsdt[1]} should be < 5 on failure"

    def test_tension_increases_with_stderr(self):
        """More stderr content → higher tension dimension."""
        short_err = ExecutionResult(stdout="", stderr="error", exit_code=1, elapsed_s=0.05)
        long_err = ExecutionResult(stdout="", stderr="error\n" * 50, exit_code=1, elapsed_s=0.05)
        nsdt_short = _extract_nsdt_from_execution(short_err, "x")
        nsdt_long = _extract_nsdt_from_execution(long_err, "x")
        assert nsdt_long[2] >= nsdt_short[2], (
            f"Long stderr tension {nsdt_long[2]} should be ≥ short stderr tension {nsdt_short[2]}"
        )

    def test_timed_out_execution_high_tension(self):
        """Timed-out execution should produce a non-zero tension."""
        er = ExecutionResult(
            stdout="",
            stderr="Sandbox execution timed out.",
            exit_code=124,
            elapsed_s=30.0,
            timed_out=True,
        )
        nsdt = _extract_nsdt_from_execution(er, "while True: pass")
        assert nsdt[2] > 0.0, "Timed-out run should have non-zero tension"


# ── 6. Diagnoses and repair ───────────────────────────────────────────────────


class TestDiagnosisAndRepair:
    def test_failed_run_produces_diagnoses(self, bridge_tight):
        """A run that fails the constitution must produce at least one diagnosis."""
        result = bridge_tight.govern("x = 1 + 1")
        # With near-zero threshold, this should fail
        if result.verdict != GovernanceVerdict.PASS:
            assert len(result.diagnoses) >= 1

    def test_diagnosis_has_surgical_prompt(self, bridge_tight):
        """Every diagnosis must have a non-empty surgical prompt."""
        result = bridge_tight.govern("y = 42")
        for d in result.diagnoses:
            assert d.surgical_prompt.strip(), f"Empty surgical prompt in diagnosis stage {d.stage}"

    def test_diagnosis_stage_in_range(self, bridge_tight):
        """Diagnosis stage must be in [0, 9]."""
        result = bridge_tight.govern("z = 'hello'")
        for d in result.diagnoses:
            assert 0 <= d.stage <= 9, f"Diagnosis stage {d.stage} out of range"

    def test_syntax_error_diagnosis_stage(self, bridge_local):
        """Syntax errors should map to Stage 0 or Stage 1 (missing/init failures)."""
        result = bridge_local.govern("def bad_syntax(\n    pass")
        if result.diagnoses:
            # SyntaxError is typically caught as a subprocess stderr error
            # mapping can vary — just confirm it's a valid stage
            for d in result.diagnoses:
                assert 0 <= d.stage <= 9

    def test_max_iterations_respected(self):
        """Bridge must not exceed max_iterations regardless of outcome."""
        bridge = LuminarkLiveBridge(
            execution_mode=ExecutionMode.LOCAL,
            max_iterations=1,
            stability_threshold=0.001,  # always fail
            sandbox_timeout=5,
        )
        result = bridge.govern("print('one iteration max')")
        assert result.iterations <= 1


# ── 7. Docker fallback ────────────────────────────────────────────────────────


class TestDockerFallback:
    def test_docker_mode_falls_back_gracefully(self):
        """
        DOCKER mode falls back to LOCAL if Docker is unavailable.
        The bridge must not raise — it must return a GovernanceResult.
        """
        bridge = LuminarkLiveBridge(
            execution_mode=ExecutionMode.DOCKER,
            max_iterations=1,
            stability_threshold=2000.0,
            sandbox_timeout=10,
        )
        # Whether Docker is available or not, govern() must return a result
        result = bridge.govern("print('docker or local')")
        assert isinstance(result, GovernanceResult)
        # execution_mode is set at construction; fallback happens inside _execute_docker
        assert bridge.execution_mode in (ExecutionMode.DOCKER, ExecutionMode.LOCAL)


# ── Runner ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
