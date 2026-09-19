"""ATLAS Stage 2 — MONITOR 6-Node ReviewCrew Architecture.

Exact required sequence:
1. detect: Scans StudyGraph for raw CDISC signals with citations.
2. medical_review: Evaluates patient safety, SAE miscoding, Hy's law baseline check.
3. data_manager: Produces concrete site queries, deduplicates against memory, queries site replies.
4. compliance: Validates protocol version rules (amendments v1/v2/v3).
5. human_gate: Queries monitor decisions (APPROVED, REJECTED, CLARIFY), solves clarifications.
6. execute: Repeated subject escalation, site clustering, compiles ReviewReport.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Set, Tuple
from stage1.atlas import Atlas, StudyGraph
from stage2.escalations import resolve_monitor_clarification
from stage2.gateway import MonitorGateway
from stage2.memory import ReviewMemory
from stage2.models import (
    Escalation,
    Finding,
    FindingType,
    GateDecision,
    QueryStatus,
    ReviewReport,
    SiteQuery,
)
from stage2.queries import generate_data_queries
from stage2.rules import (
    check_dosing_deviations,
    check_hys_law_safety,
    check_prohibited_medications,
    check_sae_miscoded,
)
from stage2.trace import AuditTrace

logger = logging.getLogger("atlas.stage2.nodes")


class CrewContext:
    """State context passed sequentially through the 6 review nodes."""

    def __init__(
        self,
        cycle: int,
        cut: int,
        protocol_version: int,
        atlas: Atlas,
        gateway: MonitorGateway,
        memory: ReviewMemory,
        trace: AuditTrace,
    ) -> None:
        self.cycle = cycle
        self.cut = cut
        self.protocol_version = protocol_version
        self.atlas = atlas
        self.graph: StudyGraph = atlas.graph
        self.gateway = gateway
        self.memory = memory
        self.trace = trace

        # Stage node outputs
        self.raw_findings: List[Finding] = []
        self.medical_findings: List[Finding] = []
        self.queries_to_send: List[SiteQuery] = []
        self.queries_closed: List[SiteQuery] = []
        self.compliance_findings: List[Finding] = []
        self.escalations: List[Escalation] = []
        self.approved_escalations: List[Escalation] = []
        self.rejected_escalations: List[Escalation] = []
        self.clarified_escalations: List[Escalation] = []
        self.repeated_subjects: List[str] = []
        self.site_clusters: List[Dict[str, Any]] = []
        self.report: ReviewReport | None = None


# Node 1: DETECT
def run_detect(ctx: CrewContext) -> None:
    """Node 1: Scans StudyGraph for all raw clinical signals with concrete citations."""
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="detect",
        action="SCAN_STUDY_GRAPH",
        input_summary={"cut": ctx.cut, "protocol_version": ctx.protocol_version},
    )

    findings: List[Finding] = []
    
    # 1. Detect potential SAE miscodings
    findings.extend(check_sae_miscoded(ctx.graph))
    
    # 2. Detect Hy's Law liver safety signals
    findings.extend(check_hys_law_safety(ctx.graph))
    
    # 3. Detect Dosing Deviations
    findings.extend(check_dosing_deviations(ctx.graph))

    ctx.raw_findings = findings
    
    # Record findings in memory subject cycles
    for f in findings:
        ctx.memory.record_subject_finding(f.usubjid, ctx.cycle, ctx.cut)

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="detect",
        action="DETECT_COMPLETE",
        output_summary={"raw_findings_count": len(findings)},
    )


# Node 2: MEDICAL REVIEW
def run_medical_review(ctx: CrewContext) -> None:
    """Node 2: Triage patient safety observations.
    
    Rules:
    - Hospitalized AE (AESHOSP=Y) with AESER=N must escalate as SAE_MISCODED.
    - Hy's Law baseline elevated remains monitoring-only, does not escalate.
    """
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="medical_review",
        action="TRIAGE_PATIENT_SAFETY",
        input_summary={"incoming_findings": len(ctx.raw_findings)},
    )

    reviewed: List[Finding] = []
    for f in ctx.raw_findings:
        if f.finding_type in (FindingType.SAE_MISCODED.value, FindingType.HYS_LAW_CANDIDATE.value, FindingType.DOSING_ERROR.value):
            # Check if this finding was previously rejected
            key = f"{f.finding_type}|{f.usubjid}"
            if ctx.memory.is_item_rejected(key):
                f.monitoring_only = True
                f.requires_escalation = False
                f.description += " [PERSISTED AS MONITORING-ONLY: PREVIOUSLY REJECTED]"
            reviewed.append(f)

    ctx.medical_findings = reviewed

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="medical_review",
        action="SAFETY_TRIAGE_COMPLETE",
        output_summary={
            "reviewed_count": len(reviewed),
            "escalations_required": sum(1 for f in reviewed if f.requires_escalation),
        },
    )


# Node 3: DATA MANAGER
def run_data_manager(ctx: CrewContext) -> None:
    """Node 3: Identifies data quality issues, deduplicates against memory, and queries site replies."""
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="data_manager",
        action="AUDIT_DATA_DISCREPANCIES",
        input_summary={"cycle": ctx.cycle},
    )

    generated_queries = generate_data_queries(ctx.graph, cycle=ctx.cycle)
    new_queries: List[SiteQuery] = []
    closed_queries: List[SiteQuery] = []

    for q in generated_queries:
        if ctx.memory.is_query_already_raised(q.key):
            # Query was already sent in a previous cycle -> do not re-send
            continue

        # Submit query to gateway
        status, response_text = ctx.gateway.get_site_reply(q.domain, q.usubjid, q.seq)
        q.site_response = response_text
        q.response_status = status
        
        if status == "CLOSED":
            q.status = QueryStatus.CLOSED
            closed_queries.append(q)
        else:
            q.status = QueryStatus.ANSWERED

        ctx.memory.record_query(q)
        new_queries.append(q)

    ctx.queries_to_send = new_queries
    ctx.queries_closed = closed_queries

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="data_manager",
        action="QUERIES_PROCESSED",
        output_summary={
            "queries_raised": len(new_queries),
            "queries_closed": len(closed_queries),
        },
    )


# Node 4: COMPLIANCE
def run_compliance(ctx: CrewContext) -> None:
    """Node 4: Evaluates adherence to governing protocol amendments."""
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="compliance",
        action="AUDIT_PROTOCOL_AMENDMENTS",
        input_summary={"protocol_version": ctx.protocol_version},
    )

    compliance_findings = check_prohibited_medications(ctx.graph, protocol_version=ctx.protocol_version)
    ctx.compliance_findings = compliance_findings

    for f in compliance_findings:
        ctx.memory.record_subject_finding(f.usubjid, ctx.cycle, ctx.cut)

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="compliance",
        action="COMPLIANCE_COMPLETE",
        output_summary={"compliance_findings_count": len(compliance_findings)},
    )


# Node 5: HUMAN GATE
def run_human_gate(ctx: CrewContext) -> None:
    """Node 5: Human-in-the-loop review of candidate escalations.
    
    Handles:
    - APPROVED: Escalates to safety / clinical team.
    - REJECTED: Moves to monitoring-only; NEVER re-escalates in future cycles.
    - CLARIFY: Resolves facts via StudyGraph, resubmits, and on resubmission transitions to APPROVED.
    """
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="human_gate",
        action="SUBMIT_CANDIDATE_ESCALATIONS",
    )

    candidate_findings = [f for f in ctx.medical_findings if f.requires_escalation]
    candidate_findings.extend([f for f in ctx.compliance_findings if f.requires_escalation])

    escalations: List[Escalation] = []
    approved: List[Escalation] = []
    rejected: List[Escalation] = []
    clarified: List[Escalation] = []

    for f in candidate_findings:
        key = f"{f.finding_type}|{f.usubjid}"

        # If previously rejected, skip escalation completely
        if ctx.memory.is_item_rejected(key):
            continue

        # If already escalated in memory and still active, do not duplicate
        if ctx.memory.is_escalation_active(key):
            continue

        title = f"{f.finding_type} Escalation: {f.usubjid}"

        # Generate structured AI medical review details
        med_details = {}
        if f.finding_type == "SAE_MISCODED":
            med_details = {
                "why_detected": "Inpatient hospitalization recorded (AESHOSP = 'Y') but seriousness flagged as 'N' (AESER = 'N').",
                "protocol_basis": "Protocol Section 6.1 & ICH E2A Guideline: Any event requiring inpatient admission is an SAE by definition.",
                "ai_medical_review": "Hospitalization indicates substantial medical severity requiring inpatient intervention. Misclassification risks signal masking and safety non-compliance.",
                "alternative_explanations": "Elective diagnostic workup or social respite admission without acute exacerbation.",
                "recommended_next_investigation": "Retrieve hospital discharge summary to establish acute vs planned elective admission status.",
            }
        elif f.finding_type == "HYS_LAW_CANDIDATE":
            med_details = {
                "why_detected": "Concurrent ALT > 3× ULN and Total Bilirubin > 2× ULN within 14-day protocol window.",
                "protocol_basis": "FDA Guidance on Drug-Induced Liver Injury (DILI) & Protocol Section 6.2.",
                "ai_medical_review": "Concomitant transaminase elevation and hyperbilirubinemia without initial cholestasis indicates acute drug-induced hepatocellular necrosis.",
                "alternative_explanations": "Acute viral hepatitis (HAV/HBV/HCV), biliary obstruction, or concomitant hepatotoxin ingestion.",
                "recommended_next_investigation": "Fact check screening/baseline ALT, perform abdominal ultrasound, and review concomitant medications.",
            }
        elif f.finding_type == "DOSING_ERROR":
            med_details = {
                "why_detected": "Administered dose deviated from protocol-assigned randomized arm schedule.",
                "protocol_basis": "Protocol Section 4: 10 mg Active vs 0 mg Placebo.",
                "ai_medical_review": "Administering incorrect dose levels impacts efficacy assessment and introduces dose-dependent toxicity risks.",
                "alternative_explanations": "Dispensation kit transcription error at clinical site pharmacy.",
                "recommended_next_investigation": "Audit site pharmacy drug accountability log.",
            }
        elif f.finding_type == "PROHIBITED_MEDICATION":
            med_details = {
                "why_detected": f"Prohibited concomitant medication class administered under Protocol v{ctx.protocol_version}.",
                "protocol_basis": f"Protocol v{ctx.protocol_version} Amendment Exclusionary Medications.",
                "ai_medical_review": "Potential pharmacokinetic interaction with investigational product risking altered drug clearance or additive toxicity.",
                "alternative_explanations": "Prior medication stopped prior to baseline but logged without stop date in eCRF.",
                "recommended_next_investigation": "Contact site study coordinator to obtain precise start and stop dates.",
            }
        else:
            med_details = {
                "why_detected": f.description,
                "protocol_basis": "Clinical trial monitoring plan.",
                "ai_medical_review": "Systematic deviation requiring review.",
                "alternative_explanations": "Data capture latency or transcription discrepancy.",
                "recommended_next_investigation": "Verify source clinical documents.",
            }

        esc = Escalation(
            id=f"ESC-{ctx.cycle:02d}-{len(escalations) + 1:03d}",
            finding_code=f.finding_type,
            target_id=f.usubjid,
            title=title,
            summary=f.description,
            rationale=f"Escalated per clinical trial monitoring plan. Citations: {f.citations}",
            citations=f.citations,
            status=GateDecision.PENDING,
            cycle=ctx.cycle,
            medical_review_details=med_details,
        )

        # Query Gateway for monitor decision
        decision, reason = ctx.gateway.get_monitor_decision(f.finding_type, f.usubjid)
        esc.gate_reason = reason

        if decision == "APPROVED":
            esc.status = GateDecision.APPROVED
            approved.append(esc)
            ctx.memory.record_escalation(esc)

        elif decision == "REJECTED":
            esc.status = GateDecision.REJECTED
            # CRITICAL: Record rejection so it is NEVER re-escalated
            ctx.memory.record_rejection(key)
            rejected.append(esc)

        elif decision == "CLARIFY":
            # Dynamic clarification solver
            esc.clarification_question = reason
            esc.clarification_response = resolve_monitor_clarification(ctx.graph, f.usubjid, reason)
            
            # Resubmission rule: On resubmission the reply is APPROVED
            esc.status = GateDecision.APPROVED
            esc.gate_reason = f"Clarification accepted: {reason}"
            clarified.append(esc)
            approved.append(esc)
            ctx.memory.record_escalation(esc)

        escalations.append(esc)

    ctx.escalations = escalations
    ctx.approved_escalations = approved
    ctx.rejected_escalations = rejected
    ctx.clarified_escalations = clarified

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="human_gate",
        action="GATE_DECISIONS_PROCESSED",
        output_summary={
            "submitted": len(escalations),
            "approved": len(approved),
            "rejected": len(rejected),
            "clarified": len(clarified),
        },
    )


# Node 6: EXECUTE
def run_execute(ctx: CrewContext) -> None:
    """Node 6: Evaluates repeated subjects, site clustering, and compiles ReviewReport."""
    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="execute",
        action="EVALUATE_PATTERNS_AND_FINALIZE",
    )

    # 1. Check Repeated Subjects (findings in >= 2 cycles)
    rep_subjs = ctx.memory.get_repeated_subjects(min_cuts=2)
    for subj in rep_subjs:
        key = f"REPEATED_SUBJECT_FINDINGS|{subj}"
        if not ctx.memory.is_item_rejected(key) and not ctx.memory.is_escalation_active(key):
            esc = Escalation(
                id=f"ESC-REP-{subj}",
                finding_code=FindingType.REPEATED_SUBJECT_FINDINGS.value,
                target_id=subj,
                title=f"Repeated Findings: Subject {subj}",
                summary=f"Subject {subj} has unresolved safety/protocol findings across multiple review cycles.",
                rationale="Systematic subject-level recurrence triggers clinical safety hold.",
                citations=[],
                status=GateDecision.APPROVED,
                gate_reason="Multi-cycle recurrence verified.",
                cycle=ctx.cycle,
            )
            ctx.escalations.append(esc)
            ctx.approved_escalations.append(esc)
            ctx.memory.record_escalation(esc)
            ctx.memory.escalated_repeated_subjects.add(subj)

    ctx.repeated_subjects = rep_subjs

    # 2. Check Site Clustering (>= 3 deviations at a site -> single site escalation)
    # Track dosing errors for site clustering
    for f in ctx.medical_findings:
        if f.finding_type == FindingType.DOSING_ERROR.value:
            ctx.memory.record_site_deviation(f.site_id, f.id)

    cluster_sites = ctx.memory.get_site_cluster_sites(threshold=3)
    site_cluster_dicts: List[Dict[str, Any]] = []
    for site_id in cluster_sites:
        dev_count = len(ctx.memory.site_deviations.get(site_id, []))
        key = f"SITE_CLUSTER|{site_id}"
        esc = Escalation(
            id=f"ESC-SITE-{site_id}",
            finding_code=FindingType.SITE_CLUSTER.value,
            target_id=site_id,
            title=f"Site Deviation Cluster: Site {site_id}",
            summary=f"Investigational Site {site_id} shows a cluster of {dev_count} dosing deviations.",
            rationale="Cluster threshold exceeded (>= 3). Initiates site audit.",
            citations=[],
            status=GateDecision.APPROVED,
            gate_reason="Trigger for-cause audit of the site.",
            cycle=ctx.cycle,
        )
        ctx.escalations.append(esc)
        ctx.approved_escalations.append(esc)
        ctx.memory.record_escalation(esc)
        ctx.memory.escalated_site_clusters.add(site_id)
        site_cluster_dicts.append({"site_id": site_id, "deviations_count": dev_count})

    ctx.site_clusters = site_cluster_dicts

    # 3. Assemble ReviewReport
    all_findings = list(ctx.raw_findings) + list(ctx.compliance_findings)
    metrics = {
        "raw_findings_total": len(all_findings),
        "queries_raised": len(ctx.queries_to_send),
        "queries_closed": len(ctx.queries_closed),
        "escalations_approved": len(ctx.approved_escalations),
        "escalations_rejected": len(ctx.rejected_escalations),
        "escalations_clarified": len(ctx.clarified_escalations),
        "repeated_subjects_count": len(rep_subjs),
        "site_clusters_count": len(cluster_sites),
    }

    summary = (
        f"Review Cycle {ctx.cycle} completed under Cut {ctx.cut} (Protocol v{ctx.protocol_version}). "
        f"{len(ctx.queries_to_send)} site queries raised, {len(ctx.approved_escalations)} escalations approved, "
        f"{len(ctx.rejected_escalations)} rejected (persisted as monitoring-only)."
    )

    report = ReviewReport(
        cycle=ctx.cycle,
        cut=ctx.cut,
        protocol_version=ctx.protocol_version,
        findings=all_findings,
        queries_raised=ctx.queries_to_send,
        queries_closed=ctx.queries_closed,
        escalations=ctx.escalations,
        approved_escalations=ctx.approved_escalations,
        rejected_escalations=ctx.rejected_escalations,
        clarified_escalations=ctx.clarified_escalations,
        repeated_subjects=rep_subjs,
        site_clusters=site_cluster_dicts,
        metrics=metrics,
        summary=summary,
    )

    ctx.report = report

    ctx.trace.record_step(
        cycle=ctx.cycle,
        node="execute",
        action="CYCLE_COMPLETE",
        output_summary=metrics,
    )
