"""Deterministic clinical finding detectors and reasoning engine for Study Sentinel."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set, Tuple

from stage1.dates import days_between, parse_date, within_window
from stage1.normalization import LabNormalizer
from stage1.rules import ProtocolRules
from starter.schemas import RecordRef


class ClinicalReasoning:
    """Deterministic clinical rule calculations, threshold checks, and event relations."""

    def __init__(self, graph: Any, rules: Optional[ProtocolRules] = None):
        self.graph = graph
        self.rules = rules or ProtocolRules.for_cut(getattr(graph, "cut", None))
        self.normalizer = LabNormalizer(graph.reference_ranges)

    def detect_hys_law_candidates(
        self,
        site_filter: Optional[str] = None,
        subject_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Detects potential Hy's law candidates.
        
        Criteria (Protocol §7):
        - ALT or AST > 3 x ULN
        - AND Total Bilirubin (BILI) > 2 x ULN
        - Within 14 days of each other
        
        Returns:
            Dict containing list of candidate subject IDs, formatted text, and evidence records.
        """
        subjects = list(self.graph.subjects.keys())
        if subject_filter:
            subjects = [s for s in subjects if s == subject_filter]
        if site_filter:
            subjects = [s for s in subjects if self.graph.subjects[s].get("site_id") == site_filter]

        candidates: List[str] = []
        evidence: List[Dict[str, Any]] = []
        explanation_lines: List[str] = []

        for usubjid in sorted(subjects):
            subj_data = self.graph.subjects[usubjid]
            site_id = subj_data.get("site_id", "")
            lb_records = self.graph.subject_domain_records.get((usubjid, "LB"), [])

            # Categorize elevations
            transaminase_elevations = []
            bili_elevations = []

            for rec in lb_records:
                testcd = rec.get("LBTESTCD", "").strip().upper()
                if testcd not in ("ALT", "AST", "BILI"):
                    continue

                raw_val = rec.get("LBORRES")
                raw_unit = rec.get("LBORRESU", "")
                norm = self.normalizer.normalize(testcd, raw_val, raw_unit, site_id)

                if norm.normalized_value is None:
                    continue

                date_val = parse_date(rec.get("LBDTC"))
                if not date_val:
                    continue

                seq = rec.get("seq")

                if testcd in ("ALT", "AST") and norm.is_above_3x_uln:
                    transaminase_elevations.append((rec, norm, date_val, seq))
                elif testcd == "BILI" and norm.is_above_2x_uln:
                    bili_elevations.append((rec, norm, date_val, seq))

            # Match within 14 days
            matching_pairs: List[Tuple[Any, Any]] = []
            for trans_rec, trans_norm, trans_date, trans_seq in transaminase_elevations:
                for bili_rec, bili_norm, bili_date, bili_seq in bili_elevations:
                    diff = abs((trans_date - bili_date).days)
                    if diff <= self.rules.hys_law_window_days:
                        matching_pairs.append((
                            (trans_rec, trans_norm, trans_date, trans_seq),
                            (bili_rec, bili_norm, bili_date, bili_seq),
                            diff
                        ))

            if matching_pairs:
                candidates.append(usubjid)
                # Select the best/first representative pair
                (trans_rec, trans_norm, trans_date, trans_seq), (bili_rec, bili_norm, bili_date, bili_seq), diff = matching_pairs[0]

                # Evidence citations
                evidence.append({"domain": "LB", "usubjid": usubjid, "seq": trans_seq})
                evidence.append({"domain": "LB", "usubjid": usubjid, "seq": bili_seq})

                # Detail description
                visit_name = trans_rec.get("VISIT") or bili_rec.get("VISIT") or "study visit"
                same_day_txt = "on the same day" if diff == 0 else f"within {diff} days"
                
                alt_txt = f"{trans_norm.testcd} {trans_norm.normalized_value} {trans_norm.normalized_unit} (>3xULN"
                if trans_norm.unit_converted:
                    alt_txt += f", converted from {trans_norm.raw_unit}"
                alt_txt += ")"

                bili_txt = f"bilirubin {bili_norm.normalized_value} {bili_norm.normalized_unit} (>2xULN)"
                line = f"For {usubjid}: {alt_txt} and {bili_txt} {same_day_txt} at {visit_name}."
                explanation_lines.append(line)

        if not candidates:
            if site_filter:
                text = f"No subjects meet Hy's law criteria at site {site_filter}."
            else:
                text = "No subjects meet potential Hy's law criteria."
            confidence = 0.95
        else:
            cand_count = len(candidates)
            summary = f"{cand_count} Hy's law candidate{'s' if cand_count > 1 else ''}. " + " ".join(explanation_lines)
            text = summary
            confidence = 0.9

        return {
            "candidates": candidates,
            "text": text,
            "evidence": evidence,
            "confidence": confidence,
        }

    def detect_dosing_errors(self, site_filter: Optional[str] = None) -> Dict[str, Any]:
        """Detects dosing deviations (Protocol §8: 10 mg for DRUG arm, 0 mg for PLACEBO)."""
        subjects = list(self.graph.subjects.keys())
        if site_filter:
            subjects = [s for s in subjects if self.graph.subjects[s].get("site_id") == site_filter]

        error_subjects: Set[str] = set()
        evidence: List[Dict[str, Any]] = []
        details: List[str] = []

        for usubjid in sorted(subjects):
            subj_data = self.graph.subjects[usubjid]
            arm = subj_data.get("arm", "").upper()
            expected_dose = self.rules.drug_arm_dose if arm == "DRUG" else self.rules.placebo_arm_dose

            ex_records = self.graph.subject_domain_records.get((usubjid, "EX"), [])
            for rec in ex_records:
                dose_str = rec.get("EXDOSE", "")
                try:
                    dose = float(str(dose_str).replace(",", "."))
                except (ValueError, TypeError):
                    continue

                if dose != expected_dose:
                    error_subjects.add(usubjid)
                    seq = rec.get("seq")
                    evidence.append({"domain": "EX", "usubjid": usubjid, "seq": seq})
                    details.append(f"{usubjid} received {dose} mg instead of {expected_dose} mg at {rec.get('VISIT')}")

        err_list = sorted(error_subjects)
        if not err_list:
            if site_filter:
                text = f"No dosing errors at site {site_filter}. The dosing errors in this study are elsewhere."
            else:
                text = "No dosing errors found."
            confidence = 0.85
        else:
            text = f"{len(err_list)} subjects with dosing errors at site {site_filter or 'all'}: {', '.join(err_list)}."
            confidence = 0.95

        return {
            "subjects": err_list,
            "count": len(err_list),
            "text": text,
            "evidence": evidence,
            "confidence": confidence,
        }

    def detect_prohibited_medications(self, site_filter: Optional[str] = None) -> Dict[str, Any]:
        """Detects prohibited concomitant medication use under active protocol rules."""
        subjects = list(self.graph.subjects.keys())
        if site_filter:
            subjects = [s for s in subjects if self.graph.subjects[s].get("site_id") == site_filter]

        violator_subjects: Set[str] = set()
        evidence: List[Dict[str, Any]] = []

        for usubjid in sorted(subjects):
            cm_records = self.graph.subject_domain_records.get((usubjid, "CM"), [])
            for rec in cm_records:
                cmclas = rec.get("CMCLAS", "").strip().upper()
                cmtrt = rec.get("CMTRT", "").strip().upper()

                is_prohibited = (
                    cmclas in self.rules.prohibited_med_classes
                    or cmtrt in self.rules.prohibited_med_terms
                )
                if is_prohibited:
                    violator_subjects.add(usubjid)
                    evidence.append({"domain": "CM", "usubjid": usubjid, "seq": rec.get("seq")})

        violators = sorted(violator_subjects)
        if not violators:
            text = f"No prohibited medications found{' at site ' + site_filter if site_filter else ''}."
            confidence = 0.9
        else:
            classes_str = ", ".join(sorted(self.rules.prohibited_med_classes))
            text = f"{len(violators)} subjects took prohibited medications ({classes_str}): {', '.join(violators)}."
            confidence = 0.95

        return {
            "subjects": violators,
            "count": len(violators),
            "text": text,
            "evidence": evidence,
            "confidence": confidence,
        }

    def detect_discontinuations_by_ae(self, site_filter: Optional[str] = None) -> Dict[str, Any]:
        """Detects subjects who discontinued study due to adverse events (DS domain)."""
        subjects = list(self.graph.subjects.keys())
        if site_filter:
            subjects = [s for s in subjects if self.graph.subjects[s].get("site_id") == site_filter]

        disc_subjects: Set[str] = set()
        evidence: List[Dict[str, Any]] = []

        for usubjid in sorted(subjects):
            ds_records = self.graph.subject_domain_records.get((usubjid, "DS"), [])
            for rec in ds_records:
                dsdecod = rec.get("DSDECOD", "").strip().upper()
                dsterm = rec.get("DSTERM", "").strip().upper()

                if dsdecod == "DISCONTINUED" and "ADVERSE" in dsterm:
                    disc_subjects.add(usubjid)
                    evidence.append({"domain": "DS", "usubjid": usubjid, "seq": rec.get("seq")})

        res_list = sorted(disc_subjects)
        count = len(res_list)
        if count == 0:
            text = f"No subjects discontinued due to an adverse event{' at site ' + site_filter if site_filter else ''}."
            confidence = 0.9
        else:
            text = f"{count} subject{'s' if count > 1 else ''} discontinued due to an adverse event: {', '.join(res_list)}."
            confidence = 0.95

        return {
            "subjects": res_list,
            "count": count,
            "text": text,
            "evidence": evidence,
            "confidence": confidence,
        }

    def detect_serious_adverse_events(self, site_filter: Optional[str] = None) -> Dict[str, Any]:
        """Detects serious adverse events (AESHOSP == 'Y' or AESER == 'Y')."""
        subjects = list(self.graph.subjects.keys())
        if site_filter:
            subjects = [s for s in subjects if self.graph.subjects[s].get("site_id") == site_filter]

        sae_subjects: Set[str] = set()
        evidence: List[Dict[str, Any]] = []

        for usubjid in sorted(subjects):
            ae_records = self.graph.subject_domain_records.get((usubjid, "AE"), [])
            for rec in ae_records:
                aeser = rec.get("AESER", "").strip().upper()
                aeshosp = rec.get("AESHOSP", "").strip().upper()

                # Protocol §6: A hospitalisation flag (AESHOSP = Y) makes an event serious
                # regardless of how AESER was coded.
                if aeser == "Y" or aeshosp == "Y":
                    sae_subjects.add(usubjid)
                    evidence.append({"domain": "AE", "usubjid": usubjid, "seq": rec.get("seq")})

        sae_list = sorted(sae_subjects)
        count = len(sae_list)
        if count == 0:
            text = f"No serious adverse events identified{' at site ' + site_filter if site_filter else ''}."
            confidence = 0.9
        else:
            text = f"{count} subjects with serious adverse events: {', '.join(sae_list)}."
            confidence = 0.95

        return {
            "subjects": sae_list,
            "count": count,
            "text": text,
            "evidence": evidence,
            "confidence": confidence,
        }

    def lookup_records_near_visit(
        self,
        usubjid: str,
        visit_name: str,
        window_days: int = 7,
        domains: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Looks up records for a subject within window_days of a specific visit."""
        target_domains = [d.upper() for d in domains] if domains else ["LB", "AE"]
        p360 = self.graph.patient360(usubjid)

        # 1. Determine visit anchor date
        anchor_date = None
        for dom in ("LB", "VS", "EX", "EG"):
            dom_recs = p360["records_by_domain"].get(dom, [])
            for rec in dom_recs:
                if rec.get("VISIT", "").strip().upper() == visit_name.strip().upper():
                    dt_str = rec.get(f"{dom}DTC") or rec.get(f"{dom}STDTC")
                    anchor_date = parse_date(dt_str)
                    if anchor_date:
                        break
            if anchor_date:
                break

        if not anchor_date:
            return {
                "answer": [],
                "text": f"Could not determine date for visit {visit_name} of subject {usubjid}.",
                "evidence": [],
                "confidence": 0.5,
            }

        matching_refs: List[Dict[str, Any]] = []
        descriptions: List[str] = []

        for dom in target_domains:
            dom_recs = p360["records_by_domain"].get(dom, [])
            for rec in dom_recs:
                dt_str = (
                    rec.get(f"{dom}DTC")
                    or rec.get(f"{dom}STDTC")
                    or rec.get("LBDTC")
                    or rec.get("AESTDTC")
                    or rec.get("VSDTC")
                )
                rec_date = parse_date(dt_str)
                if rec_date and within_window(rec_date, anchor_date, window_days):
                    seq = rec.get("seq")
                    matching_refs.append({"domain": dom, "usubjid": usubjid, "seq": seq})
                    term = rec.get("AETERM") or rec.get("LBTESTCD") or rec.get("VSTESTCD") or dom
                    descriptions.append(f"{dom}:{term} (seq {seq}) on {rec_date}")

        text = (
            f"Found {len(matching_refs)} records for {usubjid} within {window_days} days of {visit_name} ({anchor_date}): "
            + ", ".join(descriptions)
            if matching_refs
            else f"No records found for {usubjid} within {window_days} days of {visit_name}."
        )

        return {
            "answer": matching_refs,
            "text": text,
            "evidence": matching_refs,
            "confidence": 0.95,
        }
