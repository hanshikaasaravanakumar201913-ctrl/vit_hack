"""ATLAS Stage 2 — MONITOR Clinical Safety & Compliance Rules.

Deterministic rule evaluators for:
1. SAE Miscoding: AESHOSP=Y and AESER=N must escalate as SAE_MISCODED.
2. Liver Safety: Hy's Law candidate detection with baseline screening check.
   (If baseline transaminases were already elevated, keep as monitoring-only).
3. Dosing Deviations: Dose mismatch against randomized treatment arm.
4. Protocol Amendments: Prohibited concomitant medications per protocol version.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from stage1.atlas import StudyGraph
from stage2.models import Finding, FindingType


def check_sae_miscoded(graph: StudyGraph) -> List[Finding]:
    """Identifies hospitalization adverse events miscoded as non-serious (AESHOSP=Y, AESER=N).
    
    Per Protocol Section 6: Hospitalization is an absolute criterion for SAE.
    """
    findings: List[Finding] = []
    
    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom != "AE":
            continue
        
        hosp = str(rec.get("AESHOSP", "")).strip().upper()
        serious = str(rec.get("AESER", "")).strip().upper()
        
        if hosp == "Y" and serious == "N":
            term = rec.get("AETERM", "Adverse Event")
            site_id = graph.subjects.get(usubjid, {}).get("site_id", "")
            f_id = f"F-SAE-{usubjid}-{seq}"
            findings.append(Finding(
                id=f_id,
                finding_type=FindingType.SAE_MISCODED.value,
                usubjid=usubjid,
                site_id=site_id,
                citations=[("AE", usubjid, int(seq))],
                severity="HIGH",
                description=f"Subject hospitalized for '{term}' (AESHOSP=Y) but miscoded as non-serious (AESER=N).",
                raw_data=rec,
                requires_escalation=True,
                monitoring_only=False,
                metadata={"term": term, "seq": seq},
            ))
            
    return findings


def check_hys_law_safety(graph: StudyGraph) -> List[Finding]:
    """Identifies Hy's Law candidates with screening baseline transaminase precision check.
    
    Rule:
    - ALT > 3x ULN (or AST > 3x ULN) AND BILI > 2x ULN within 14 days.
    - Precision Rule: Check baseline screening ALT/AST.
      If transaminases were already elevated at screening, mark as monitoring-only, do not escalate!
    """
    findings: List[Finding] = []

    # Map subject -> list of LB records
    subj_labs: Dict[str, List[Dict[str, Any]]] = {}
    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom == "LB":
            subj_labs.setdefault(usubjid, []).append(rec)

    for usubjid, labs in subj_labs.items():
        site_id = graph.subjects.get(usubjid, {}).get("site_id", "")
        
        # 1. Identify post-baseline transaminase & bilirubin peak elevations
        alt_elevations = []
        bili_elevations = []
        screening_elevated = False

        for rec in labs:
            test = str(rec.get("LBTESTCD", "")).strip().upper()
            vis = str(rec.get("VISIT", "")).strip().upper()
            val_str = str(rec.get("LBORRES", "")).strip()
            unit = str(rec.get("LBORRESU", "")).strip()
            dt_str = str(rec.get("LBDTC", "")).strip()
            seq = int(rec.get("seq", rec.get("LBSEQ", 1)))

            try:
                val = float(val_str)
            except ValueError:
                continue

            # Standardize units for S07 (ukat/L -> U/L x60)
            if unit in ("ukat/L", "μkat/L"):
                val_ul = val * 60.0
            else:
                val_ul = val

            is_screening = ("SCREEN" in vis or "SCR" in vis)

            # Transaminase thresholds: Central ALT > 56 U/L, AST > 40 U/L
            # Hy's law criterion: > 3x ULN -> ALT > 168 U/L, AST > 120 U/L
            # For S07 ukat/L: ULN is 0.93 ukat/L -> 3x is 2.79 ukat/L
            is_transam_3x = False
            if test == "ALT":
                is_transam_3x = (val_ul > 168.0) if unit not in ("ukat/L", "μkat/L") else (val > 2.79)
            elif test == "AST":
                is_transam_3x = (val_ul > 120.0) if unit not in ("ukat/L", "μkat/L") else (val > 2.01)

            if is_screening and is_transam_3x:
                screening_elevated = True

            if not is_screening and is_transam_3x:
                alt_elevations.append((dt_str, test, val, unit, seq, rec))

            # Bilirubin threshold: Central BILI > 1.2 mg/dL. Hy's law: > 2x ULN -> > 2.4 mg/dL
            if test == "BILI" and val > 2.4 and not is_screening:
                bili_elevations.append((dt_str, val, unit, seq, rec))

        # Check for co-occurrence within 14 days
        qualifying_pair = None
        for (a_dt, a_test, a_val, a_unit, a_seq, a_rec) in alt_elevations:
            for (b_dt, b_val, b_unit, b_seq, b_rec) in bili_elevations:
                # If dates exist, verify <= 14 days difference
                days_diff = 0
                if a_dt and b_dt:
                    try:
                        d1 = datetime.date.fromisoformat(a_dt)
                        d2 = datetime.date.fromisoformat(b_dt)
                        days_diff = abs((d1 - d2).days)
                    except ValueError:
                        days_diff = 0
                if days_diff <= 14:
                    qualifying_pair = (a_test, a_val, a_unit, a_seq, b_val, b_unit, b_seq, days_diff)
                    break
            if qualifying_pair:
                break

        if qualifying_pair:
            a_test, a_val, a_unit, a_seq, b_val, b_unit, b_seq, diff = qualifying_pair
            citations = [("LB", usubjid, a_seq), ("LB", usubjid, b_seq)]
            f_id = f"F-HYSL-{usubjid}"

            if screening_elevated:
                # Baseline transaminases were already elevated -> monitoring-only
                findings.append(Finding(
                    id=f_id,
                    finding_type=FindingType.HYS_LAW_CANDIDATE.value,
                    usubjid=usubjid,
                    site_id=site_id,
                    citations=citations,
                    severity="LOW",
                    description=f"Hy's law biochemical threshold met ({a_test} {a_val} {a_unit}, BILI {b_val} mg/dL) but baseline transaminases were already elevated; monitor, do not escalate.",
                    requires_escalation=False,
                    monitoring_only=True,
                    metadata={"screening_elevated": True, "days_diff": diff},
                ))
            else:
                # True candidate -> requires safety escalation
                findings.append(Finding(
                    id=f_id,
                    finding_type=FindingType.HYS_LAW_CANDIDATE.value,
                    usubjid=usubjid,
                    site_id=site_id,
                    citations=citations,
                    severity="HIGH",
                    description=f"Potential Hy's law candidate: {a_test} {a_val} {a_unit} (>3x ULN) and BILI {b_val} mg/dL (>2x ULN) within {diff} days.",
                    requires_escalation=True,
                    monitoring_only=False,
                    metadata={"screening_elevated": False, "days_diff": diff},
                ))

    return findings


def check_dosing_deviations(graph: StudyGraph) -> List[Finding]:
    """Identifies administrations discordant with randomized treatment arm."""
    findings: List[Finding] = []

    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom != "EX":
            continue

        sdata = graph.subjects.get(usubjid, {})
        arm = str(sdata.get("arm", "")).strip().upper()
        site_id = sdata.get("site_id", "")
        dose_str = str(rec.get("EXDOSE", "")).strip()

        try:
            dose = float(dose_str)
        except ValueError:
            continue

        is_deviation = False
        expected = 10.0 if "DRUG" in arm or "10" in arm else 0.0
        if "DRUG" in arm and dose != 10.0:
            is_deviation = True
        elif "PLACEBO" in arm and dose != 0.0:
            is_deviation = True

        if is_deviation:
            f_id = f"F-DOSE-{usubjid}-{seq}"
            findings.append(Finding(
                id=f_id,
                finding_type=FindingType.DOSING_ERROR.value,
                usubjid=usubjid,
                site_id=site_id,
                citations=[("EX", usubjid, int(seq))],
                severity="HIGH",
                description=f"Dose mismatch: Received {dose} mg despite assignment to {arm} (expected {expected} mg).",
                raw_data=rec,
                requires_escalation=True,
                monitoring_only=False,
                metadata={"administered": dose, "expected": expected, "arm": arm},
            ))

    return findings


def check_prohibited_medications(graph: StudyGraph, protocol_version: int = 3) -> List[Finding]:
    """Identifies prohibited concomitant medications under the governing protocol version."""
    findings: List[Finding] = []

    # Prohibited classes by version:
    # v1: Prednisolone / Glucocorticoids
    # v2: Prednisolone / Glucocorticoids
    # v3: Prednisolone + Glibenclamide / Sulfonylureas
    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom != "CM":
            continue

        trt = str(rec.get("CMTRT", "")).strip().upper()
        cls_name = str(rec.get("CMCLAS", "")).strip().upper()
        site_id = graph.subjects.get(usubjid, {}).get("site_id", "")

        is_prohibited = False
        reason = ""

        if "PREDNISOLONE" in trt or "GLUCOCORTICOID" in cls_name:
            is_prohibited = True
            reason = "Systemic glucocorticoids prohibited across all protocol versions."
        elif protocol_version >= 3 and ("GLIBENCLAMIDE" in trt or "SULFONYLUREA" in cls_name):
            is_prohibited = True
            reason = "Sulfonylureas (Glibenclamide) prohibited under Protocol Amendment 3."

        if is_prohibited:
            f_id = f"F-CM-{usubjid}-{seq}"
            findings.append(Finding(
                id=f_id,
                finding_type=FindingType.PROHIBITED_MEDICATION.value,
                usubjid=usubjid,
                site_id=site_id,
                citations=[("CM", usubjid, int(seq))],
                severity="MEDIUM",
                description=f"Prohibited concomitant medication '{trt}': {reason}",
                raw_data=rec,
                requires_escalation=True,
                monitoring_only=False,
                metadata={"treatment": trt, "protocol_version": protocol_version},
            ))

    return findings
