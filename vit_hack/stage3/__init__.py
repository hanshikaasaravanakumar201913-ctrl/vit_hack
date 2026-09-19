"""ATLAS Stage 3 — WATCH Package.

Mandatory architecture: stage3 imports stage2 (which imports stage1).
Provides incremental multi-cut surveillance, data integrity detection,
suspicious site detection, protocol amendment tracking, and trace-backed explanations.
"""

# Mandatory specification import
import stage2

from stage3.models import (
    BudgetState,
    DataIntegrityFinding,
    ProtocolDiff,
    SurveillanceCutReport,
    SuspiciousSiteFinding,
    WatchDecision,
    WatchDecisionStatus,
)
from stage3.budget import BudgetManager
from stage3.detectors import (
    DataIntegrityDetector,
    ProtocolAmendmentDetector,
    SuspiciousSiteDetector,
)
from stage3.corrections import CorrectionsManager
from stage3.watch import WatchSurveillance

__all__ = [
    "stage2",
    "BudgetState",
    "DataIntegrityFinding",
    "ProtocolDiff",
    "SurveillanceCutReport",
    "SuspiciousSiteFinding",
    "WatchDecision",
    "WatchDecisionStatus",
    "BudgetManager",
    "DataIntegrityDetector",
    "ProtocolAmendmentDetector",
    "SuspiciousSiteDetector",
    "CorrectionsManager",
    "WatchSurveillance",
]
