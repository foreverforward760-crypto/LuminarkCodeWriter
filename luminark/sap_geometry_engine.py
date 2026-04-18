"""
sap_geometry_engine.py – SAP Geometry Engine
LUMINARK Active Governance Layer

Canonical 10-stage state-space classification using the Stanfield Axiom of
Perpetuity (SAP). Provides:

  - STAGE_METADATA: per-stage names, geometry, arc, stability flags
  - STAGE_CENTROIDS: canonical 5D NSDT centroid coordinates
  - ADJACENCY_MATRIX: hard transition law (no skipping, Stage 5 irreversible,
    Stage 8 terminal branch)
  - SAPGeometry: classification, micro-position, and transition enforcement
"""

import math

import numpy as np

# ── Stage metadata ────────────────────────────────────────────────────────────

STAGE_METADATA: dict[int, dict] = {
    0: {
        "name": "Plenara",
        "geometry": "Sphere",
        "arc": "neutral",
        "physical_stability": True,
        "conscious_stability": True,
        "tumbling_coeff": 0.1,
    },
    1: {
        "name": "The Spark",
        "geometry": "Point",
        "arc": "descending",
        "physical_stability": False,
        "conscious_stability": True,
        "tumbling_coeff": 0.2,
    },
    2: {
        "name": "The Vessel",
        "geometry": "Line",
        "arc": "descending",
        "physical_stability": True,
        "conscious_stability": False,
        "tumbling_coeff": 0.3,
    },
    3: {
        "name": "The Engine",
        "geometry": "Triangle",
        "arc": "descending",
        "physical_stability": False,
        "conscious_stability": True,
        "tumbling_coeff": 0.4,
    },
    4: {
        "name": "The Crucible",
        "geometry": "Square",
        "arc": "descending",
        "physical_stability": True,
        "conscious_stability": False,
        "tumbling_coeff": 0.5,
    },
    5: {
        "name": "The Dynamo",
        "geometry": "Pentagon",
        "arc": "bifurcation",
        "physical_stability": False,
        "conscious_stability": True,
        "tumbling_coeff": 0.6,
    },
    6: {
        "name": "The Nexus",
        "geometry": "Hexagon",
        "arc": "ascending",
        "physical_stability": True,
        "conscious_stability": False,
        "tumbling_coeff": 0.7,
    },
    7: {
        "name": "The Lens",
        "geometry": "Heptagon",
        "arc": "ascending",
        "physical_stability": False,
        "conscious_stability": True,
        "tumbling_coeff": 0.8,
    },
    8: {
        "name": "The Vessel of Grounding",
        "geometry": "Octagon",
        "arc": "ascending",
        "physical_stability": True,
        "conscious_stability": False,
        "tumbling_coeff": 0.9,
    },
    9: {
        "name": "The Transparency",
        "geometry": "Nonagon",
        "arc": "ascending",
        "physical_stability": False,
        "conscious_stability": True,
        "tumbling_coeff": 1.0,
    },
}

# ── Canonical centroids (5D NSDT: Complexity, Stability, Tension, Adaptability, Coherence)

STAGE_CENTROIDS: dict[int, list[float]] = {
    0: [0.0, 0.0, 0.0, 0.0, 0.0],
    1: [1.0, 8.0, 1.0, 1.0, 1.0],
    2: [2.0, 7.0, 2.0, 2.0, 2.0],
    3: [4.0, 7.0, 2.5, 3.0, 4.0],
    4: [3.5, 6.5, 3.0, 3.5, 5.0],
    5: [5.0, 4.0, 5.0, 5.0, 4.5],
    6: [6.0, 5.5, 4.0, 6.0, 6.5],
    7: [6.5, 3.0, 7.0, 7.0, 3.5],
    8: [7.5, 7.0, 8.0, 2.0, 2.0],
    9: [8.0, 2.0, 8.5, 1.5, 1.5],
}

AXIS_WEIGHTS: list[float] = [1.0, 1.5, 1.5, 1.0, 0.8]
AXIS_SCALES: list[float] = [10.0, 10.0, 10.0, 10.0, 10.0]

# ── Adjacency matrix ──────────────────────────────────────────────────────────

ADJACENCY_MATRIX = np.zeros((10, 10))
for _i in range(10):
    ADJACENCY_MATRIX[_i, _i] = 1.0  # self-loop
    if _i > 0:
        ADJACENCY_MATRIX[_i, _i - 1] = 1.0  # backward ±1
    if _i < 9:
        ADJACENCY_MATRIX[_i, _i + 1] = 1.0  # forward ±1

# Hard SAP rules
ADJACENCY_MATRIX[5, :5] = 0.0  # Stage 5: point of no return
ADJACENCY_MATRIX[8, :] = 0.0  # Stage 8: terminal branch only
ADJACENCY_MATRIX[8, 8] = 1.0
ADJACENCY_MATRIX[8, 9] = 1.0


# ── Geometry class ────────────────────────────────────────────────────────────


class SAPGeometry:
    """
    SAP state-space geometry: classification, micro-position, transition law.
    """

    @staticmethod
    def weighted_distance(v1: list[float], v2: list[float]) -> float:
        """Weighted normalised Euclidean distance between two NSDT vectors."""
        return math.sqrt(
            sum(AXIS_WEIGHTS[i] * ((v1[i] - v2[i]) / AXIS_SCALES[i]) ** 2 for i in range(5))
        )

    @staticmethod
    def classify(x: list[float]) -> int:
        """Return the dominant SAP stage (nearest centroid)."""
        distances = {s: SAPGeometry.weighted_distance(x, c) for s, c in STAGE_CENTROIDS.items()}
        return min(distances, key=distances.get)

    @staticmethod
    def all_distances(x: list[float]) -> dict[int, float]:
        return {s: SAPGeometry.weighted_distance(x, c) for s, c in STAGE_CENTROIDS.items()}

    @staticmethod
    def get_adjacency() -> np.ndarray:
        return ADJACENCY_MATRIX.copy()

    @staticmethod
    def is_transition_allowed(prev: int | None, new: int) -> tuple[bool, str]:
        if prev is None:
            return True, "initial"
        if ADJACENCY_MATRIX[prev, new] > 0:
            return True, f"allowed {prev}→{new}"
        return False, f"geometric violation {prev}→{new}"

    @staticmethod
    def enforce_geometry(prev: int | None, new: int) -> tuple[int, bool]:
        """
        Hard-enforce transition law. Returns (corrected_stage, was_valid).
        """
        if prev is None:
            return new, True
        delta = new - prev
        if prev == 5 and new < 5:
            return 5, False  # point of no return
        if delta > 1:
            return prev + 1, False  # no skipping forward
        if delta < -1:
            return prev - 1, False  # no skipping backward
        return new, True

    @staticmethod
    def compute_micro_position(x: list[float], stage: int) -> float:
        """
        Continuous position on the centroid axis [stage, stage+1].
        Returns float in [stage, stage+1].
        """
        if stage == 9:
            c_cur = STAGE_CENTROIDS[9]
            c_next = STAGE_CENTROIDS[0]
            d_tot = SAPGeometry.weighted_distance(c_cur, c_next)
            d_next = SAPGeometry.weighted_distance(x, c_next)
            return 9.0 + (1.0 - d_next / max(d_tot, 1e-9)) * 0.99

        c_cur = STAGE_CENTROIDS[stage]
        c_next = STAGE_CENTROIDS[stage + 1]
        direction = [c_next[i] - c_cur[i] for i in range(5)]
        observed = [x[i] - c_cur[i] for i in range(5)]

        dot_num = sum(
            AXIS_WEIGHTS[i] * observed[i] * direction[i] / (AXIS_SCALES[i] ** 2) for i in range(5)
        )
        dot_den = sum(AXIS_WEIGHTS[i] * direction[i] ** 2 / (AXIS_SCALES[i] ** 2) for i in range(5))
        t = max(0.0, min(1.0, dot_num / dot_den)) if dot_den > 0 else 0.0
        return stage + t

    @staticmethod
    def get_metadata(stage: int) -> dict:
        return STAGE_METADATA.get(stage, {})

    @staticmethod
    def arc(stage: int) -> str:
        return STAGE_METADATA[stage]["arc"]
