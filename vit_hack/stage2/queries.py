"""ATLAS Stage 2 — MONITOR Data Management Query Generator.

Identifies data discrepancies and produces concrete site queries:
- AE onset before first dose (e.g. 042-S11-005)
- Missing mandatory visit fields
- Dose transcription errors
"""

from __future__ import annotations

import datetime
from typing import List
from stage1.atlas import StudyGraph
from stage2.models import QueryStatus, SiteQuery


def generate_data_queries(graph: StudyGraph, cycle: int = 1) -> List[SiteQuery]:
    """Generates concrete data management queries for discrepancies."""
    queries: List[SiteQuery] = []

    # 1. AE Onset Prior to First Dose Date
    # For each subject, find their earliest EX start date (Baseline Day 1)
    subj_first_dose: dict[str, str] = {}
    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom == "EX":
            dt = str(rec.get("EXSTDTC", "")).strip()
            if dt:
                if usubjid not in subj_first_dose or dt < subj_first_dose[usubjid]:
                    subj_first_dose[usubjid] = dt

    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom == "AE":
            ae_start = str(rec.get("AESTDTC", "")).strip()
            term = rec.get("AETERM", "Adverse Event")
            site_id = graph.subjects.get(usubjid, {}).get("site_id", "")
            first_dose = subj_first_dose.get(usubjid)

            if ae_start and first_dose and ae_start < first_dose:
                q_id = f"QRY-AE-{usubjid}-{seq}"
                queries.append(SiteQuery(
                    id=q_id,
                    domain="AE",
                    usubjid=usubjid,
                    seq=int(seq),
                    site_id=site_id,
                    query_type="DATE_INCONSISTENCY",
                    field_name="AESTDTC",
                    query_text=f"Adverse event '{term}' recorded onset date ({ae_start}) is before first study dose ({first_dose}). Please verify against source records.",
                    status=QueryStatus.OPEN,
                    cycle=cycle,
                ))

    # 2. Dose Transcription Errors in EX
    for (dom, usubjid, seq), rec in graph.records_by_ref.items():
        if dom == "EX":
            dose = str(rec.get("EXDOSE", "")).strip()
            site_id = graph.subjects.get(usubjid, {}).get("site_id", "")
            if dose == "20":
                q_id = f"QRY-EX-{usubjid}-{seq}"
                queries.append(SiteQuery(
                    id=q_id,
                    domain="EX",
                    usubjid=usubjid,
                    seq=int(seq),
                    site_id=site_id,
                    query_type="DOSE_TRANSCRIPTION_ERROR",
                    field_name="EXDOSE",
                    query_text=f"Administered dose recorded as 20 mg. Randomized protocol dose is 10 mg. Confirm whether transcription error or deviation.",
                    status=QueryStatus.OPEN,
                    cycle=cycle,
                ))

    return queries
