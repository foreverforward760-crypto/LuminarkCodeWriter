"""
sap_constrained_bayesian.py – Constrained Bayesian SAP Inference
LUMINARK Active Governance Layer

Computes a posterior distribution over 10 SAP stages using:
  1. Weighted centroid-distance logits
  2. Trap energy modulation (per-stage energy field)
  3. Hard geometric adjacency masking (forbidden transitions → -inf)
  4. Softmax with calibrated temperature

Trap Energy function (SAPEnergy) is integrated here so the posterior is already
deformed by the energy landscape before any downstream analysis.
"""


import numpy as np

from sap_geometry_engine import (
    ADJACENCY_MATRIX,
    AXIS_SCALES,
    AXIS_WEIGHTS,
    STAGE_CENTROIDS,
    STAGE_METADATA,
    SAPGeometry,
)

# ── Trap Energy ───────────────────────────────────────────────────────────────

class SAPEnergy:
    """
    Per-stage trap energy field.
    Deforms the probability landscape: high-energy stages become less probable
    under the Bayesian posterior, unless the NSDT vector is close to the trap.

    Energy values in [0.0, 1.0].
    """

    @staticmethod
    def trap_energy(stage: int, x: list[float]) -> float:
        """Geometry-derived trap potential for a given stage."""
        c, s, t, a, coh = x[0], x[1], x[2], x[3], x[4]

        if stage == 8:   # False heaven / false hell
            return max(0.0, min(1.0, (2.0 * coh - 1.5 * a + 1.2 * s) / 5.0))
        if stage == 7:   # Permanent isolation
            return max(0.0, min(1.0, (1.5 * t - 1.0 * a) / 5.0))
        if stage == 5:   # Stagnation at bifurcation
            return max(0.0, min(1.0, (4.0 - a) * (1.0 - (c + coh) / 20.0) / 4.0))
        if stage == 3:   # Avoidance disguised as discipline
            return max(0.0, min(1.0, (a - 7.0) * (4.0 - coh) / 30.0))
        return 0.0

    @staticmethod
    def compute_total_energy(x: list[float], posterior: np.ndarray) -> float:
        """
        E[trap_energy] over the posterior distribution.
        Returns value in [0, 1].
        """
        return float(sum(
            posterior[s] * SAPEnergy.trap_energy(s, x)
            for s in range(10)
        ))

    @staticmethod
    def compute_gradient(x: list[float], posterior: np.ndarray,
                         epsilon: float = 1e-5) -> list[float]:
        """
        Finite-difference gradient of total energy w.r.t. each NSDT dimension.
        Returns list of 5 floats — used for intervention targeting.
        """
        grad = []
        for i in range(5):
            x_plus = list(x)
            x_plus[i] += epsilon
            x_minus = list(x)
            x_minus[i] -= epsilon
            e_plus  = SAPEnergy.compute_total_energy(x_plus,  posterior)
            e_minus = SAPEnergy.compute_total_energy(x_minus, posterior)
            grad.append((e_plus - e_minus) / (2.0 * epsilon))
        return grad

    @staticmethod
    def modulate_logits(logits: np.ndarray, x: list[float],
                        beta: float = 0.8) -> np.ndarray:
        """Deform the probability landscape with energy potentials."""
        energies = np.array([SAPEnergy.trap_energy(s, x) for s in range(10)])
        return logits - beta * energies


# ── Constrained Bayesian ──────────────────────────────────────────────────────

class SAPConstrainedBayesian:
    """
    Bayesian SAP posterior:
      P_modulated(s|x) ∝ P_raw(s|x) · exp(-β·E(s,x))
    with hard geometric masking.

    Parameters
    ----------
    temperature : float — softmax temperature (default 0.5)
    beta        : float — energy modulation coefficient (default 0.8)
    """

    def __init__(self, temperature: float = 0.5, beta: float = 0.8):
        self.temperature = temperature
        self.beta        = beta
        self._centroids  = {k: np.array(v, dtype=float)
                            for k, v in STAGE_CENTROIDS.items()}
        self._weights    = np.array(AXIS_WEIGHTS)
        self._scales     = np.array(AXIS_SCALES)

    def _raw_logits(self, x: np.ndarray) -> np.ndarray:
        return np.array([
            -float(np.sqrt(np.sum(
                self._weights * ((x - c) / self._scales) ** 2
            )))
            for c in self._centroids.values()
        ])

    def posterior(self, x: np.ndarray,
                  prev_stage: int | None = None) -> np.ndarray:
        """
        Compute posterior over 10 stages.
        Applies energy modulation then geometric masking.
        """
        logits = self._raw_logits(x)
        logits = SAPEnergy.modulate_logits(logits, x.tolist(), self.beta)

        # Hard geometric mask
        if prev_stage is not None:
            mask   = ADJACENCY_MATRIX[prev_stage]
            logits = np.where(mask > 0, logits, -np.inf)

        # Softmax with temperature
        temp       = max(self.temperature, 0.05)
        logits_t   = logits / temp
        finite     = logits_t[np.isfinite(logits_t)]
        if len(finite) == 0:
            return np.ones(10) / 10.0
        logits_t  -= np.max(finite)
        exp        = np.where(np.isfinite(logits_t), np.exp(logits_t), 0.0)
        total      = exp.sum()
        if total == 0:
            return np.ones(10) / 10.0
        return exp / total

    def forward(self, x: list[float],
                prev_stage: int | None = None) -> dict:
        """
        Full forward pass — returns all SAP quantities.

        Returns
        -------
        dict with:
            posterior       : List[float] — 10-class probability distribution
            dominant_stage  : int
            expected_stage  : float
            entropy         : float — Shannon entropy (nats)
            trap_energy     : float — E[trap] under posterior
            energy_gradient : List[float] — ∂E/∂x (5D)
            arc             : str
            geometric_valid : bool
            stage_metadata  : dict
        """
        x_arr    = np.array(x, dtype=float)
        post     = self.posterior(x_arr, prev_stage)
        dominant = int(np.argmax(post))
        expected = float(np.sum(np.arange(10) * post))
        entropy  = float(-np.sum(post * np.log(post + 1e-12)))
        trap_e   = SAPEnergy.compute_total_energy(x, post)
        trap_g   = SAPEnergy.compute_gradient(x, post)
        meta     = STAGE_METADATA.get(dominant, {})

        geo_valid = True
        if prev_stage is not None:
            _, msg    = SAPGeometry.is_transition_allowed(prev_stage, dominant)
            geo_valid = not msg.startswith("geometric violation")

        return {
            "posterior":        post.tolist(),
            "dominant_stage":   dominant,
            "expected_stage":   round(expected, 4),
            "entropy":          round(entropy, 4),
            "trap_energy":      round(trap_e, 4),
            "energy_gradient":  [round(g, 6) for g in trap_g],
            "arc":              meta.get("arc", "unknown"),
            "geometric_valid":  geo_valid,
            "stage_metadata":   {
                "name":     meta.get("name", ""),
                "geometry": meta.get("geometry", ""),
                "arc":      meta.get("arc", ""),
            },
        }
