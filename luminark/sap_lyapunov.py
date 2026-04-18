"""
sap_lyapunov.py – Lyapunov Stability Monitor
LUMINARK Active Governance Layer

Implements the Lyapunov stability layer for the Numerical Constitution:

  V(x) = w_H · H(x) + w_E · E(x) + w_v · v(x)²

Where:
  H(x) = entropy of posterior distribution (information disorder)
  E(x) = total trap energy expectation over posterior
  v(x) = stage velocity (rate of stage change over time)

The governance guarantee: if dV/dt < 0 the system is moving toward equilibrium.
If dV/dt > 0 the LuminarkLiveBridge must escalate to surgical intervention.

Classes:
  LyapunovController        – V(), recommend_action(), lyapunov_decrease()
  LyapunovVulnerabilityScanner – scan_code_path() for trace-based dV/dt detection
  NumericalConstitution     – stability certificate: passes/fails governance check
"""

from dataclasses import dataclass

import numpy as np

# ── Lyapunov Controller ───────────────────────────────────────────────────────

class LyapunovController:
    """
    Lyapunov stability controller.

    V(H, E, v) = w_H·H + w_E·E + w_v·v²

    All terms are non-negative; V = 0 only at equilibrium.
    Recommended action is chosen to strictly decrease V.
    """

    def __init__(self, w_H: float = 1.0, w_E: float = 2.0, w_v: float = 0.5):
        self.w_H = w_H
        self.w_E = w_E
        self.w_v = w_v

    def V(self, entropy: float, energy: float, velocity: float) -> float:  # noqa: N802
        """Compute Lyapunov function value. V ≥ 0."""
        return self.w_H * entropy + self.w_E * energy + self.w_v * (velocity ** 2)

    def dV(  # noqa: N802
        self,
           entropy_before: float, energy_before: float, velocity_before: float,
           entropy_after:  float, energy_after:  float, velocity_after:  float,
    ) -> float:  # noqa: N802
        """
        Compute dV = V_after - V_before.
        Negative value = system moving toward equilibrium (good).
        Positive value = diverging — escalate to intervention.
        """
        return (self.V(entropy_after, energy_after, velocity_after) -
                self.V(entropy_before, energy_before, velocity_before))

    def lyapunov_decrease(self,
                          entropy_before: float, energy_before: float, velocity_before: float,
                          entropy_after:  float, energy_after:  float, velocity_after:  float,
    ) -> float:  # noqa: N802
        """Alias: positive = V decreased (stabilising); negative = V increased (diverging)."""
        return -self.dV(entropy_before, energy_before, velocity_before,
                        entropy_after,  energy_after,  velocity_after)

    def recommend_action(self,
                         entropy: float,
                         energy:  float,
                         velocity: float,
                         cynical_loop: bool = False) -> str:
        """
        Defense action: HOLD / DAMPEN / INTERVENE / BREAK_PATTERN.
        Chosen to strictly decrease V under reasonable assumptions.
        """
        if cynical_loop:
            return "BREAK_PATTERN"
        v = self.V(entropy, energy, velocity)
        if v > 5.0:
            return "INTERVENE"
        if v > 2.0:
            return "DAMPEN"
        return "HOLD"

    def is_stable(self, entropy: float, energy: float, velocity: float,
                  threshold: float = 3.0) -> bool:
        """Return True if V is below the stability threshold."""
        return self.V(entropy, energy, velocity) < threshold


# ── Lyapunov Vulnerability Scanner ───────────────────────────────────────────

class LyapunovVulnerabilityScanner:
    """
    Scans NSDT time-series traces for dV/dt > 0 windows —
    potential instability candidates in code execution or system behaviour.

    trace shape    : (N, 5) — NSDT vectors over time, values in [0, 10]
    timestamps shape: (N,)  — unix timestamps
    """

    def __init__(self, w_H: float = 1.0, w_E: float = 2.0, w_v: float = 0.5,
                 instability_threshold: float = 0.2):
        self.controller = LyapunovController(w_H=w_H, w_E=w_E, w_v=w_v)
        self.instability_threshold = instability_threshold

    def _row_to_lyapunov_inputs(self, row: np.ndarray, velocity: float) -> tuple[float, float, float]:
        """
        Map a 5D NSDT row to (entropy_proxy, energy_proxy, velocity).
        entropy_proxy: std of normalised values (information disorder proxy)
        energy_proxy:  (tension + (1 - adaptability)) / 2
        """
        row_norm      = row / 10.0
        entropy_proxy = float(np.std(row_norm))
        energy_proxy  = float((row_norm[2] + (1.0 - row_norm[3])) / 2.0)
        return entropy_proxy, energy_proxy, velocity

    def scan_code_path(self, trace: np.ndarray, timestamps: np.ndarray) -> dict:
        """
        Scan a trace for instability windows (dV/dt > threshold).

        Returns dict with:
            vulnerabilities   : list of dicts
            v_series          : list of V values
            instability_count : int
        """
        if trace.ndim != 2 or trace.shape[1] < 5:
            return {"vulnerabilities": [], "v_series": [],
                    "instability_count": 0, "error": "trace must be (N, 5)"}

        v_series: list[float] = []
        vulnerabilities: list[dict] = []
        prev_v: float | None = None

        for i in range(len(trace)):
            row = trace[i, :5]
            if i == 0:
                velocity = 0.0
            else:
                dt       = max(1e-3, float(timestamps[i] - timestamps[i - 1]))
                velocity = float(np.mean(np.abs(trace[i, :5] - trace[i - 1, :5]))) / dt

            ep, eng, vel = self._row_to_lyapunov_inputs(row, velocity)
            v_val = self.controller.V(ep, eng, vel)
            v_series.append(round(v_val, 5))

            if prev_v is not None:
                dv = v_val - prev_v
                if dv > self.instability_threshold:
                    vulnerabilities.append({
                        "index":        i,
                        "timestamp":    float(timestamps[i]),
                        "dV":           round(dv, 5),
                        "V":            round(v_val, 5),
                        "state_vector": row[:5].tolist(),
                        "severity":     "HIGH" if dv > self.instability_threshold * 2 else "MODERATE",
                    })
            prev_v = v_val

        return {
            "vulnerabilities":   vulnerabilities,
            "v_series":          v_series,
            "instability_count": len(vulnerabilities),
        }


# ── Numerical Constitution ────────────────────────────────────────────────────

@dataclass
class StabilityReport:
    passed:      bool
    V:           float
    action:      str
    entropy:     float
    energy:      float
    velocity:    float
    message:     str

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict of this stability report."""
        return {
            "passed":   self.passed,
            "V":        self.V,
            "action":   self.action,
            "entropy":  self.entropy,
            "energy":   self.energy,
            "velocity": self.velocity,
            "message":  self.message,
        }

    def __str__(self) -> str:
        status = "✅ STABLE" if self.passed else "❌ UNSTABLE"
        return (f"{status} | V={self.V:.4f} | action={self.action} | "
                f"H={self.entropy:.3f} E={self.energy:.3f} v={self.velocity:.3f} | "
                f"{self.message}")


class NumericalConstitution:
    """
    Governance stability certificate.

    Evaluates a Lyapunov function against the constitutional stability threshold.
    A LUMINARK code execution must PASS the constitution before its output is
    accepted. Failure triggers escalation to the SAPPsychiatrist.
    """

    def __init__(self, controller: LyapunovController | None = None,
                 stability_threshold: float = 3.0,
                 intervention_threshold: float = 5.0):
        self.controller             = controller or LyapunovController()
        self.stability_threshold    = stability_threshold
        self.intervention_threshold = intervention_threshold

    def certify(self, entropy: float, energy: float, velocity: float) -> StabilityReport:
        """
        Issue a stability certificate for the given system state.

        Returns StabilityReport:
            passed=True  if V < stability_threshold  (PASS)
            passed=False if V ≥ stability_threshold  (FAIL — escalate)
        """
        V      = self.controller.V(entropy, energy, velocity)
        action = self.controller.recommend_action(entropy, energy, velocity)
        passed = self.stability_threshold > V

        if passed:
            message = "System within constitutional stability bounds."
        elif self.intervention_threshold > V:
            message = ("V exceeds stability threshold — DAMPEN required. "
                       "Escalate to SAPPsychiatrist for surgical prompt.")
        else:
            message = ("V exceeds intervention threshold — CRITICAL. "
                       "Emergency intervention required. Stage progression blocked.")

        return StabilityReport(
            passed=passed,
            V=round(V, 6),
            action=action,
            entropy=round(entropy, 6),
            energy=round(energy, 6),
            velocity=round(velocity, 6),
            message=message,
        )

    def certify_from_trace(self, entropy: float, energy: float,
                            velocity: float) -> bool:
        """Convenience: returns True if certify() passes."""
        return self.certify(entropy, energy, velocity).passed
