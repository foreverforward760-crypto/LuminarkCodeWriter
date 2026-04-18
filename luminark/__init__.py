"""
luminark – LUMINARK Active Governance Layer
Stanfield's Axiom of Perpetuity (SAP) — Production Package

Public API:
    from luminark import SAPGeometry, SAPConstrainedBayesian, SAPEnergy
    from luminark import LyapunovController, NumericalConstitution
    from luminark import SAPPsychiatrist, SAPDiagnosis
    from luminark import LuminarkLiveBridge, ExecutionMode, GovernanceVerdict
"""

from luminark.luminark_live_bridge import (
    ExecutionMode,
    GovernanceResult,
    GovernanceVerdict,
    LuminarkLiveBridge,
)
from luminark.sap_constrained_bayesian import (
    SAPConstrainedBayesian,
    SAPEnergy,
)
from luminark.sap_geometry_engine import (
    ADJACENCY_MATRIX,
    AXIS_SCALES,
    AXIS_WEIGHTS,
    STAGE_CENTROIDS,
    STAGE_METADATA,
    SAPGeometry,
)
from luminark.sap_lyapunov import (
    LyapunovController,
    LyapunovVulnerabilityScanner,
    NumericalConstitution,
    StabilityReport,
)
from luminark.sap_stage_classifier import (
    SAPDiagnosis,
    SAPPsychiatrist,
)

__version__ = "1.0.0"
__author__ = "Richard L. Stanfield"
__org__ = "Meridian Axiom Alignment Technologies (MAAT)"

__all__ = [
    # Geometry
    "SAPGeometry",
    "STAGE_CENTROIDS",
    "STAGE_METADATA",
    "ADJACENCY_MATRIX",
    "AXIS_WEIGHTS",
    "AXIS_SCALES",
    # Bayesian + Energy
    "SAPConstrainedBayesian",
    "SAPEnergy",
    # Lyapunov
    "LyapunovController",
    "LyapunovVulnerabilityScanner",
    "NumericalConstitution",
    "StabilityReport",
    # Psychiatrist
    "SAPPsychiatrist",
    "SAPDiagnosis",
    # Bridge
    "LuminarkLiveBridge",
    "ExecutionMode",
    "GovernanceVerdict",
    "GovernanceResult",
    # Meta
    "__version__",
    "__author__",
    "__org__",
]
