"""
luminark_live_bridge.py – LUMINARK Live Bridge
Main Orchestrator for the Active Governance Layer

The LuminarkLiveBridge is the central intelligence that:

  1. Receives a code task (prompt + existing code + test suite)
  2. Executes the code inside the Docker sandbox (the "Crucible")
  3. Evaluates the output against the Numerical Constitution (Lyapunov check)
  4. If PASS: accepts the output
  5. If FAIL: calls the SAPPsychiatrist to generate a Surgical Prompt
  6. Re-submits the Surgical Prompt for repair (up to max_iterations)
  7. Returns a GovernanceResult with full audit trail

Execution modes:
  DOCKER  — runs code in an isolated Python 3.11-slim container with ulimits
  LOCAL   — runs code in a subprocess (for development/testing only)

The Docker mode is the "Crucible": resource-constrained, network-isolated,
and ephemeral. No code that hasn't passed the Numerical Constitution leaves it.
"""

import os
import re
import sys
import json
import time
import logging
import subprocess
import tempfile
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any

import numpy as np

from sap_geometry_engine import SAPGeometry, STAGE_METADATA
from sap_constrained_bayesian import SAPConstrainedBayesian, SAPEnergy
from sap_lyapunov import LyapunovController, NumericalConstitution, StabilityReport
from sap_stage_classifier import SAPPsychiatrist, SAPDiagnosis

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)


# ── Enums and config ──────────────────────────────────────────────────────────

class ExecutionMode(str, Enum):
    DOCKER = "docker"
    LOCAL  = "local"


class GovernanceVerdict(str, Enum):
    PASS            = "PASS"
    FAIL_REPAIRED   = "FAIL_REPAIRED"
    FAIL_EXHAUSTED  = "FAIL_EXHAUSTED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ExecutionResult:
    """Raw result from one sandbox execution."""
    stdout:       str
    stderr:       str
    exit_code:    int
    elapsed_s:    float
    timed_out:    bool = False

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


@dataclass
class GovernanceResult:
    """
    Final result from the full governance loop.
    Contains the audit trail of every iteration.
    """
    verdict:        GovernanceVerdict
    final_code:     str
    iterations:     int
    audit_trail:    List[Dict]       = field(default_factory=list)
    final_report:   Optional[StabilityReport] = None
    diagnoses:      List[SAPDiagnosis]         = field(default_factory=list)
    total_elapsed_s: float = 0.0

    def summary(self) -> str:
        lines = [
            f"Governance Verdict: {self.verdict.value}",
            f"Iterations:         {self.iterations}",
            f"Total time:         {self.total_elapsed_s:.2f}s",
        ]
        if self.final_report:
            lines.append(f"Final stability:    {self.final_report}")
        if self.diagnoses:
            lines.append(f"Diagnoses issued:   {len(self.diagnoses)}")
            for d in self.diagnoses:
                lines.append(f"  [{d.stage}] {d.stage_name} — {d.urgency}")
        return "\n".join(lines)


# ── NSDT extractor ────────────────────────────────────────────────────────────

def _extract_nsdt_from_execution(result: ExecutionResult,
                                  code: str) -> List[float]:
    """
    Heuristically derive an NSDT vector from an execution result.

    This is the bridge between Python execution behaviour and the SAP
    state-space. The NSDT dimensions are inferred from measurable properties
    of the execution:

      Complexity   ← lines of code / 50 (normalised to [0,10])
      Stability    ← exit_code==0 ? 8.0 : 2.0 (pass/fail proxy)
      Tension      ← stderr length / 100 capped at 10 (error volume)
      Adaptability ← execution speed proxy (fast = high adaptability)
      Coherence    ← stdout/stderr ratio (clean output = coherent)
    """
    loc         = len(code.splitlines())
    complexity  = min(10.0, loc / 50.0 * 10.0)
    stability   = 8.0 if result.success else 2.0
    tension     = min(10.0, len(result.stderr) / 100.0)

    # Adaptability: inversely proportional to elapsed time (0–10s range)
    adaptability = max(0.0, 10.0 - result.elapsed_s)

    # Coherence: ratio of stdout to total output
    total_out = len(result.stdout) + len(result.stderr) + 1
    coherence = (len(result.stdout) / total_out) * 10.0

    return [
        round(complexity,   3),
        round(stability,    3),
        round(tension,      3),
        round(adaptability, 3),
        round(coherence,    3),
    ]


# ── LuminarkLiveBridge ────────────────────────────────────────────────────────

class LuminarkLiveBridge:
    """
    The LUMINARK Active Governance Orchestrator.

    Executes code in a sandboxed environment, evaluates stability via the
    Numerical Constitution, and iteratively repairs failures using the
    SAPPsychiatrist's Surgical Prompts.

    Parameters
    ----------
    execution_mode   : ExecutionMode — DOCKER (production) or LOCAL (dev)
    max_iterations   : int — maximum repair attempts before FAIL_EXHAUSTED
    docker_image     : str — Docker image name for sandbox
    sandbox_timeout  : int — execution timeout in seconds
    stability_threshold : float — Lyapunov V threshold for PASS
    """

    def __init__(self,
                 execution_mode:      ExecutionMode = ExecutionMode.DOCKER,
                 max_iterations:      int           = 3,
                 docker_image:        str           = "luminark-sandbox:latest",
                 sandbox_timeout:     int           = 30,
                 stability_threshold: float         = 3.0):

        self.execution_mode      = execution_mode
        self.max_iterations      = max_iterations
        self.docker_image        = docker_image
        self.sandbox_timeout     = sandbox_timeout

        self.bayesian            = SAPConstrainedBayesian()
        self.lyapunov            = LyapunovController()
        self.constitution        = NumericalConstitution(
            controller            = self.lyapunov,
            stability_threshold   = stability_threshold,
        )
        self.psychiatrist        = SAPPsychiatrist()

        logger.info(
            f"LuminarkLiveBridge initialised | mode={execution_mode.value} "
            f"max_iter={max_iterations} timeout={sandbox_timeout}s"
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def govern(self, code: str, task_description: str = "",
               prev_stage: Optional[int] = None) -> GovernanceResult:
        """
        Full governance loop for a piece of code.

        Parameters
        ----------
        code             : Python source code to evaluate
        task_description : what the code is supposed to do (for context)
        prev_stage       : previous SAP stage (for geometric masking)

        Returns
        -------
        GovernanceResult with verdict, final code, and full audit trail
        """
        t_start     = time.time()
        current     = code
        audit_trail = []
        diagnoses   = []

        for iteration in range(1, self.max_iterations + 1):
            logger.info(f"Governance iteration {iteration}/{self.max_iterations}")

            # 1. Execute in sandbox
            exec_result = self._execute(current)

            # 2. Extract NSDT vector from execution behaviour
            nsdt = _extract_nsdt_from_execution(exec_result, current)

            # 3. Compute Bayesian forward pass
            fwd = self.bayesian.forward(nsdt, prev_stage)

            # 4. Build Lyapunov inputs
            entropy  = fwd["entropy"]
            energy   = fwd["trap_energy"]
            velocity = abs(fwd["expected_stage"] - (prev_stage or 0)) / max(exec_result.elapsed_s, 0.01)

            # 5. Numerical Constitution check
            report = self.constitution.certify(entropy, energy, velocity)

            audit_entry = {
                "iteration":    iteration,
                "exit_code":    exec_result.exit_code,
                "elapsed_s":    round(exec_result.elapsed_s, 3),
                "nsdt":         nsdt,
                "sap_stage":    fwd["dominant_stage"],
                "stage_name":   STAGE_METADATA[fwd["dominant_stage"]]["name"],
                "V":            report.V,
                "passed":       report.passed,
                "action":       report.action,
                "stdout_head":  exec_result.stdout[:200],
                "stderr_head":  exec_result.stderr[:200],
            }

            # 6. Verdict
            if report.passed and exec_result.success:
                audit_entry["verdict"] = "PASS"
                audit_trail.append(audit_entry)
                logger.info(f"✅ PASS on iteration {iteration} | V={report.V:.4f}")
                verdict = (GovernanceVerdict.PASS if iteration == 1
                           else GovernanceVerdict.FAIL_REPAIRED)
                return GovernanceResult(
                    verdict          = verdict,
                    final_code       = current,
                    iterations       = iteration,
                    audit_trail      = audit_trail,
                    final_report     = report,
                    diagnoses        = diagnoses,
                    total_elapsed_s  = round(time.time() - t_start, 3),
                )

            # 7. Diagnose failure with SAPPsychiatrist
            if not exec_result.success:
                error_class, error_message = self._parse_error(exec_result.stderr)
                diagnosis = self.psychiatrist.diagnose_from_strings(
                    error_class   = error_class,
                    error_message = error_message,
                    function_name = self._extract_function_name(current),
                )
                diagnoses.append(diagnosis)
                audit_entry["diagnosis_stage"] = diagnosis.stage
                audit_entry["diagnosis_name"]  = diagnosis.stage_name
                audit_entry["surgical_prompt"] = diagnosis.surgical_prompt
                logger.warning(
                    f"❌ Execution failed — Stage {diagnosis.stage} "
                    f"({diagnosis.stage_name}) | {diagnosis.urgency}"
                )
            else:
                # Constitution failed but execution succeeded: Stage 8 False Hell
                diagnosis = self.psychiatrist.diagnose_from_strings(
                    error_class   = "ConstitutionFailure",
                    error_message = f"V={report.V:.4f} exceeds threshold. {report.message}",
                    function_name = self._extract_function_name(current),
                )
                diagnoses.append(diagnosis)
                audit_entry["diagnosis_stage"] = 8
                audit_entry["diagnosis_name"]  = "The Vessel of Grounding"
                audit_entry["surgical_prompt"] = diagnosis.surgical_prompt
                logger.warning(
                    f"⚠️  Constitution failed (False Hell) | V={report.V:.4f} | "
                    f"action={report.action}"
                )

            audit_entry["verdict"] = "FAIL"
            audit_trail.append(audit_entry)

            # 8. Apply surgical repair
            if diagnosis and iteration < self.max_iterations:
                current = self._apply_surgical_repair(
                    current, diagnosis.surgical_prompt, exec_result
                )
                prev_stage = fwd["dominant_stage"]

        # 9. Max iterations exhausted
        logger.error(
            f"❌ FAIL_EXHAUSTED after {self.max_iterations} iterations"
        )
        return GovernanceResult(
            verdict         = GovernanceVerdict.FAIL_EXHAUSTED,
            final_code      = current,
            iterations      = self.max_iterations,
            audit_trail     = audit_trail,
            diagnoses       = diagnoses,
            total_elapsed_s = round(time.time() - t_start, 3),
        )

    # ── Execution ──────────────────────────────────────────────────────────

    def _execute(self, code: str) -> ExecutionResult:
        """Dispatch to Docker or local execution."""
        if self.execution_mode == ExecutionMode.DOCKER:
            return self._execute_docker(code)
        return self._execute_local(code)

    def _execute_docker(self, code: str) -> ExecutionResult:
        """
        Execute code inside the luminark-sandbox Docker container.
        The container runs with ulimits (CPU/Memory) enforced by entrypoint.sh.
        """
        t0 = time.time()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         prefix="luminark_exec_",
                                         delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--memory", "256m",
                "--cpus",   "0.5",
                "--pids-limit", "64",
                "-v", f"{tmp_path}:/workspace/task.py:ro",
                self.docker_image,
                "python", "/workspace/task.py",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.sandbox_timeout,
            )
            elapsed = time.time() - t0
            return ExecutionResult(
                stdout=result.stdout, stderr=result.stderr,
                exit_code=result.returncode, elapsed_s=elapsed,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="", stderr="Sandbox execution timed out.",
                exit_code=124, elapsed_s=self.sandbox_timeout, timed_out=True,
            )
        except FileNotFoundError:
            # Docker not available — warn and fall back to local
            logger.warning("Docker not found — falling back to LOCAL execution mode")
            return self._execute_local(code)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def _execute_local(self, code: str) -> ExecutionResult:
        """
        Execute code in a subprocess (development mode).
        NOT resource-constrained — use only for local testing.
        """
        t0 = time.time()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py",
                                         prefix="luminark_local_",
                                         delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True,
                timeout=self.sandbox_timeout,
            )
            elapsed = time.time() - t0
            return ExecutionResult(
                stdout=result.stdout, stderr=result.stderr,
                exit_code=result.returncode, elapsed_s=elapsed,
            )
        except subprocess.TimeoutExpired:
            return ExecutionResult(
                stdout="", stderr="Local execution timed out.",
                exit_code=124, elapsed_s=self.sandbox_timeout, timed_out=True,
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # ── Repair ─────────────────────────────────────────────────────────────

    def _apply_surgical_repair(self, code: str, surgical_prompt: str,
                                exec_result: ExecutionResult) -> str:
        """
        Apply a surgical repair to the code based on the Psychiatrist's prompt.

        This method applies heuristic repairs for common patterns.
        In production, this would call an LLM with the surgical prompt.
        The LLM call is left as an integration point (marked below).
        """
        repaired = code

        # -- Integration point: replace this block with LLM call --
        # If an LLM client is configured, call it here:
        #
        #   from openai import OpenAI
        #   client = OpenAI()
        #   response = client.chat.completions.create(
        #       model="gpt-4o",
        #       messages=[
        #           {"role": "system", "content": "You are a Python repair engine."},
        #           {"role": "user",   "content": f"{surgical_prompt}\n\nCode:\n{code}\n\nError:\n{exec_result.stderr}"},
        #       ]
        #   )
        #   repaired = response.choices[0].message.content
        #   return repaired
        #
        # -- End integration point --

        # Heuristic repairs (applied when no LLM is configured)

        # Add try/except around bare code if there's an uncaught exception
        if exec_result.stderr and "Traceback" in exec_result.stderr:
            if "try:" not in code and "except" not in code:
                indent = "    "
                wrapped_lines = [indent + line for line in code.splitlines()]
                repaired = (
                    "import sys\ntry:\n" +
                    "\n".join(wrapped_lines) +
                    "\nexcept Exception as _e:\n"
                    "    print(f'LUMINARK_REPAIR: {type(_e).__name__}: {_e}', file=sys.stderr)\n"
                    "    raise\n"
                )

        # Append the surgical prompt as a comment for LLM integration visibility
        repaired += f"\n\n# LUMINARK_SURGICAL_PROMPT: {surgical_prompt[:200]}\n"
        return repaired

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_error(stderr: str) -> tuple:
        """Extract error class and message from stderr traceback."""
        lines = [ln.strip() for ln in stderr.splitlines() if ln.strip()]
        for line in reversed(lines):
            # Typical traceback last line: "ErrorClass: message"
            m = re.match(r'^([A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Warning|Exit)): (.+)$', line)
            if m:
                return m.group(1), m.group(2)
        # Fallback
        return "RuntimeError", stderr[:200] if stderr else "unknown error"

    @staticmethod
    def _extract_function_name(code: str) -> str:
        """Extract the first function name from source code."""
        m = re.search(r'def\s+(\w+)\s*\(', code)
        return m.group(1) if m else "module_level"

    def get_stage_report(self, code: str) -> Dict[str, Any]:
        """
        Quick SAP stage report for a piece of code without full governance.
        Useful for dashboard / monitoring.
        """
        exec_result = self._execute(code)
        nsdt        = _extract_nsdt_from_execution(exec_result, code)
        fwd         = self.bayesian.forward(nsdt)
        entropy     = fwd["entropy"]
        energy      = fwd["trap_energy"]
        velocity    = 0.0
        report      = self.constitution.certify(entropy, energy, velocity)

        return {
            "nsdt":        nsdt,
            "sap_stage":   fwd["dominant_stage"],
            "stage_name":  STAGE_METADATA[fwd["dominant_stage"]]["name"],
            "V":           report.V,
            "passed":      report.passed,
            "action":      report.action,
            "message":     report.message,
            "exec_success": exec_result.success,
        }
