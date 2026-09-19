"""ATLAS Stage 2 — MONITOR Core Data Models.

Defines deterministic data structures for the 6-node ReviewCrew architecture:
Findings, Site Queries, Escalations, Trace Entries, and Review Reports.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


class FindingType(str, Enum):
    SAE_MISCODED = "SAE_MISCODED"
    SAE_UNESCALATED = "SAE_UNESCALATED"
    HYS_LAW_CANDIDATE = "HYS_LAW_CANDIDATE"
    DOSING_ERROR = "DOSING_ERROR"
    PROHIBITED_MEDICATION = "PROHIBITED_MEDICATION"
    DUPLICATE_SUBJECT = "DUPLICATE_SUBJECT"
    IMPLAUSIBLE_SITE_PATTERN = "IMPLAUSIBLE_SITE_PATTERN"
    REPEATED_SUBJECT_FINDINGS = "REPEATED_SUBJECT_FINDINGS"
    SITE_CLUSTER = "SITE_CLUSTER"
    DATA_INCONSISTENCY = "DATA_INCONSISTENCY"


class GateDecision(str, Enum):
    PENDING = "PENDING"
    FACT_CHECK_REQUESTED = "FACT_CHECK_REQUESTED"
    FACT_CHECK_COMPLETE = "FACT_CHECK_COMPLETE"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    MONITORING = "MONITORING"
    EXECUTED = "EXECUTED"
    CLARIFY = "CLARIFY"


class QueryStatus(str, Enum):
    OPEN = "OPEN"
    SENT = "SENT"
    ANSWERED = "ANSWERED"
    CLOSED = "CLOSED"


@dataclass
class Finding:
    """A deterministic clinical anomaly or safety observation identified during review."""
    id: str
    finding_type: str
    usubjid: str
    site_id: str
    citations: List[Tuple[str, str, int]] = field(default_factory=list)
    severity: str = "MEDIUM"  # HIGH, MEDIUM, LOW
    description: str = ""
    raw_data: Dict[str, Any] = field(default_factory=dict)
    requires_escalation: bool = False
    monitoring_only: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "finding_type": self.finding_type,
            "usubjid": self.usubjid,
            "site_id": self.site_id,
            "citations": self.citations,
            "severity": self.severity,
            "description": self.description,
            "raw_data": self.raw_data,
            "requires_escalation": self.requires_escalation,
            "monitoring_only": self.monitoring_only,
            "metadata": self.metadata,
        }


@dataclass
class SiteQuery:
    """A formal data management query issued to a clinical site."""
    id: str
    domain: str
    usubjid: str
    seq: int
    site_id: str
    query_type: str
    field_name: str
    query_text: str
    status: QueryStatus = QueryStatus.OPEN
    site_response: Optional[str] = None
    response_status: Optional[str] = None  # CLOSED, ANSWERED
    cycle: int = 1
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    @property
    def key(self) -> str:
        return f"{self.domain}|{self.usubjid}|{self.seq}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "domain": self.domain,
            "usubjid": self.usubjid,
            "seq": self.seq,
            "site_id": self.site_id,
            "query_type": self.query_type,
            "field_name": self.field_name,
            "query_text": self.query_text,
            "status": self.status.value if isinstance(self.status, QueryStatus) else str(self.status),
            "site_response": self.site_response,
            "response_status": self.response_status,
            "cycle": self.cycle,
            "created_at": self.created_at,
        }


@dataclass
class Escalation:
    """A clinical safety or compliance issue submitted to the human medical monitor."""
    id: str
    finding_code: str
    target_id: str  # USUBJID or SITEID
    title: str
    summary: str
    rationale: str
    citations: List[Tuple[str, str, int]] = field(default_factory=list)
    status: GateDecision = GateDecision.PENDING
    gate_reason: Optional[str] = None
    clarification_question: Optional[str] = None
    clarification_response: Optional[str] = None
    cycle: int = 1
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    # Human Medical Monitor & AI Review extensions
    fact_check_query: Optional[str] = None
    fact_check_result: Optional[Dict[str, Any]] = None
    monitor_comments: List[Dict[str, Any]] = field(default_factory=list)
    suggested_action: Optional[str] = None
    medical_review_details: Dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.finding_code}|{self.target_id}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "key": self.key,
            "finding_code": self.finding_code,
            "target_id": self.target_id,
            "title": self.title,
            "summary": self.summary,
            "rationale": self.rationale,
            "citations": self.citations,
            "status": self.status.value if isinstance(self.status, GateDecision) else str(self.status),
            "gate_reason": self.gate_reason,
            "clarification_question": self.clarification_question,
            "clarification_response": self.clarification_response,
            "fact_check_query": self.fact_check_query,
            "fact_check_result": self.fact_check_result,
            "monitor_comments": self.monitor_comments,
            "suggested_action": self.suggested_action,
            "medical_review_details": self.medical_review_details,
            "cycle": self.cycle,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class TraceEntry:
    """Immutable audit trail entry for each ReviewCrew node execution."""
    entry_id: str
    cycle: int
    node: str
    timestamp: str
    action: str
    input_summary: Dict[str, Any] = field(default_factory=dict)
    output_summary: Dict[str, Any] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "cycle": self.cycle,
            "node": self.node,
            "timestamp": self.timestamp,
            "action": self.action,
            "input_summary": self.input_summary,
            "output_summary": self.output_summary,
            "details": self.details,
        }


@dataclass
class ReviewReport:
    """Final comprehensive output generated by a single ReviewCrew review cycle."""
    cycle: int
    cut: int
    protocol_version: int
    findings: List[Finding] = field(default_factory=list)
    queries_raised: List[SiteQuery] = field(default_factory=list)
    queries_closed: List[SiteQuery] = field(default_factory=list)
    escalations: List[Escalation] = field(default_factory=list)
    approved_escalations: List[Escalation] = field(default_factory=list)
    rejected_escalations: List[Escalation] = field(default_factory=list)
    clarified_escalations: List[Escalation] = field(default_factory=list)
    repeated_subjects: List[str] = field(default_factory=list)
    site_clusters: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cycle": self.cycle,
            "cut": self.cut,
            "protocol_version": self.protocol_version,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "metrics": self.metrics,
            "findings_count": len(self.findings),
            "queries_raised_count": len(self.queries_raised),
            "queries_closed_count": len(self.queries_closed),
            "escalations_count": len(self.escalations),
            "approved_escalations_count": len(self.approved_escalations),
            "rejected_escalations_count": len(self.rejected_escalations),
            "clarified_escalations_count": len(self.clarified_escalations),
            "repeated_subjects": self.repeated_subjects,
            "site_clusters": self.site_clusters,
            "findings": [f.to_dict() for f in self.findings],
            "queries_raised": [q.to_dict() for q in self.queries_raised],
            "queries_closed": [q.to_dict() for q in self.queries_closed],
            "escalations": [e.to_dict() for e in self.escalations],
            "approved_escalations": [e.to_dict() for e in self.approved_escalations],
            "rejected_escalations": [e.to_dict() for e in self.rejected_escalations],
            "clarified_escalations": [e.to_dict() for e in self.clarified_escalations],
        }
