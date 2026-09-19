"""ATLAS Stage 3 — WATCH Surveillance Core Data Models.

Defines data structures for incremental multi-cut surveillance:
- WatchDecision: Explainable surveillance decision linked to immutable traces.
- BudgetState: Processing budget degradation state (HEALTHY, LIMITED, CRITICAL).
- SurveillanceCutReport: Longitudinal report per data cut.
- SuspiciousSiteFinding: Measurable statistical anomalies across clinical sites.
- DataIntegrityFinding: Laboratory analyser anomalies vs clinical patient emergencies.
- ProtocolDiff: Protocol amendments and affected findings.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

# Mandatory architecture import: stage3 imports stage2
import stage2
from stage2.models import Finding, SiteQuery, Escalation, GateDecision, TraceEntry
from starter.schemas import RecordRef


class BudgetState(str, Enum):
    """Global execution budget tiers with graceful degradation."""
    HEALTHY = "HEALTHY"      # > 30% budget remaining: full deep reasoning & explanations
    LIMITED = "LIMITED"      # 10% - 30% remaining: prioritize safety/data checks, reduce narrative
    CRITICAL = "CRITICAL"    # < 10% remaining: mandatory deterministic checks only, finish gracefully


class WatchDecisionStatus(str, Enum):
    """Explicit human monitor and surveillance decision states."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CLARIFY = "CLARIFY"
    UNANSWERED = "UNANSWERED"
    ACTED_UNDER_STANDING_LIMITS = "ACTED_UNDER_STANDING_LIMITS"
    MONITORING = "MONITORING"
    EXECUTED = "EXECUTED"


@dataclass
class WatchDecision:
    """An explainable, trace-backed surveillance decision made by WATCH or the human monitor."""
    decision_id: str                      # e.g. "D-001", "D-012"
    cut: int                              # Cut number 1 to 12
    finding_code: str                     # Finding type code
    target_id: str                        # USUBJID or Site ID
    title: str                            # Concise title
    decision: WatchDecisionStatus = WatchDecisionStatus.PENDING
    action: str = ""                      # Action taken or recommended
    rationale: str = ""                   # Detailed clinical or data integrity rationale
    rule_basis: str = ""                  # Protocol rule or statistical criterion
    evidence: List[Union[RecordRef, Tuple[str, str, int], Dict[str, Any]]] = field(default_factory=list)
    evidence_details: List[Dict[str, Any]] = field(default_factory=list)
    alternatives: List[str] = field(default_factory=list)
    trace: List[Dict[str, Any]] = field(default_factory=list)
    superseded_by: Optional[str] = None   # Newer decision ID if corrected
    previous_decision_id: Optional[str] = None # Prior decision ID if this is an update
    monitor_response: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        formatted_evidence = []
        for ev in self.evidence:
            if isinstance(ev, RecordRef):
                formatted_evidence.append(ev.to_dict())
            elif isinstance(ev, tuple) and len(ev) == 3:
                formatted_evidence.append({"domain": ev[0], "usubjid": ev[1], "seq": ev[2]})
            elif isinstance(ev, dict):
                formatted_evidence.append(ev)
            else:
                formatted_evidence.append(str(ev))

        return {
            "decision_id": self.decision_id,
            "cut": self.cut,
            "finding_code": self.finding_code,
            "target_id": self.target_id,
            "title": self.title,
            "decision": self.decision.value if isinstance(self.decision, WatchDecisionStatus) else str(self.decision),
            "action": self.action,
            "rationale": self.rationale,
            "rule_basis": self.rule_basis,
            "evidence": formatted_evidence,
            "evidence_count": len(formatted_evidence),
            "evidence_details": self.evidence_details,
            "alternatives": self.alternatives,
            "trace": self.trace,
            "superseded_by": self.superseded_by,
            "previous_decision_id": self.previous_decision_id,
            "monitor_response": self.monitor_response,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class SuspiciousSiteFinding:
    """A data-driven statistical anomaly indicating potential reporting irregularities or fabrication."""
    site_id: str
    signal: str                           # e.g. "UNNATURAL_LOW_VARIABILITY"
    cut: int
    metric_name: str                      # e.g. "SYSBP_STDEV"
    observed_value: float                 # e.g. 0.71 mmHg
    cohort_mean: float                    # e.g. 8.95 mmHg
    p_value_heuristic: float              # Statistical deviation score
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    assessment: str = ""
    recommended_action: str = ""
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "site_id": self.site_id,
            "signal": self.signal,
            "cut": self.cut,
            "metric_name": self.metric_name,
            "observed_value": round(self.observed_value, 2),
            "cohort_mean": round(self.cohort_mean, 2),
            "p_value_heuristic": self.p_value_heuristic,
            "evidence": self.evidence,
            "evidence_count": len(self.evidence),
            "assessment": self.assessment,
            "recommended_action": self.recommended_action,
            "trace_id": self.trace_id,
        }


@dataclass
class DataIntegrityFinding:
    """Distinguishes data / laboratory analyser anomalies from genuine clinical safety emergencies."""
    finding_id: str
    site_id: str
    cut: int
    test_code: str                        # e.g. "GLUC"
    reported_unit: str                    # e.g. "mg/dL"
    inferred_true_unit: str               # e.g. "mmol/L"
    conversion_factor: float              # e.g. 18.018
    is_clinical_emergency: bool = False   # False = Data Integrity issue; True = Patient Safety Emergency
    adversarial_note_present: bool = False
    adversarial_note_text: str = ""
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    affected_subjects: List[str] = field(default_factory=list)
    assessment: str = ""
    recommended_action: str = ""
    trace_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "site_id": self.site_id,
            "cut": self.cut,
            "test_code": self.test_code,
            "reported_unit": self.reported_unit,
            "inferred_true_unit": self.inferred_true_unit,
            "conversion_factor": self.conversion_factor,
            "is_clinical_emergency": self.is_clinical_emergency,
            "adversarial_note_present": self.adversarial_note_present,
            "adversarial_note_text": self.adversarial_note_text,
            "affected_subjects": self.affected_subjects,
            "affected_count": len(self.affected_subjects),
            "evidence": self.evidence,
            "evidence_count": len(self.evidence),
            "assessment": self.assessment,
            "recommended_action": self.recommended_action,
            "trace_id": self.trace_id,
        }


@dataclass
class ProtocolDiff:
    """Represents changes between protocol versions and their impact on historical findings."""
    from_version: int
    to_version: int
    effective_cut: int
    amendments: List[Dict[str, str]] = field(default_factory=list)
    affected_finding_types: List[str] = field(default_factory=list)
    affected_subjects: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_version": self.from_version,
            "to_version": self.to_version,
            "effective_cut": self.effective_cut,
            "amendments": self.amendments,
            "affected_finding_types": self.affected_finding_types,
            "affected_subjects": self.affected_subjects,
            "summary": self.summary,
        }


@dataclass
class SurveillanceCutReport:
    """Comprehensive surveillance report for a single data cut."""
    cut: int
    protocol_version: int
    new_records_count: int
    corrections_count: int
    budget_state: BudgetState
    decisions: List[WatchDecision] = field(default_factory=list)
    suspicious_sites: List[SuspiciousSiteFinding] = field(default_factory=list)
    data_integrity_findings: List[DataIntegrityFinding] = field(default_factory=list)
    protocol_diff: Optional[ProtocolDiff] = None
    summary: str = ""
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cut": self.cut,
            "protocol_version": self.protocol_version,
            "new_records_count": self.new_records_count,
            "corrections_count": self.corrections_count,
            "budget_state": self.budget_state.value if isinstance(self.budget_state, BudgetState) else str(self.budget_state),
            "summary": self.summary,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "decisions_count": len(self.decisions),
            "suspicious_sites_count": len(self.suspicious_sites),
            "data_integrity_count": len(self.data_integrity_findings),
            "decisions": [d.to_dict() for d in self.decisions],
            "suspicious_sites": [s.to_dict() for s in self.suspicious_sites],
            "data_integrity_findings": [di.to_dict() for di in self.data_integrity_findings],
            "protocol_diff": self.protocol_diff.to_dict() if self.protocol_diff else None,
        }
