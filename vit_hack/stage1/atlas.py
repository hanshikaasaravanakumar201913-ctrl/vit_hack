"""Stage 1 - ATLAS: StudyGraph and Atlas Question Answering Engine.

This module implements:
- StudyGraph: In-memory clinical knowledge graph and multi-domain index.
- Atlas: Deterministic question answering engine proving answers with verified RecordRefs.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from stage1.dates import parse_date, within_window
from stage1.evidence import EvidenceValidator
from stage1.normalization import LabNormalizer
from stage1.reasoning import ClinicalReasoning
from stage1.rules import ProtocolRules
from starter.schemas import Answer, Question, RecordRef

logger = logging.getLogger(__name__)


class StudyGraph:
    """In-memory clinical study knowledge graph and index.
    
    Joins subjects, sites, visits, and clinical domain records (DM, AE, LB, VS,
    EX, CM, DS, MH, EG) while supporting data-cut filtering and official
    record corrections.
    """

    KNOWN_DOMAINS = ["DM", "AE", "LB", "VS", "EX", "CM", "DS", "MH", "EG"]

    def __init__(self, data_dir: str):
        """Initializes the StudyGraph with the path to the study data directory.
        
        Args:
            data_dir: Path to directory containing study files or a 'data' subfolder.
        """
        self.raw_data_dir = data_dir
        self.data_dir = self._resolve_data_dir(data_dir)
        self.cut: Optional[int] = None
        
        # Core data indices
        # (domain, usubjid, seq) -> record dictionary
        self.records_by_ref: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
        # usubjid -> Subject metadata dictionary
        self.subjects: Dict[str, Dict[str, Any]] = {}
        # (usubjid, domain) -> list of record dictionaries
        self.subject_domain_records: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        # usubjid -> visit -> list of record dictionaries
        self.subject_visits: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
        
        # Reference and control data
        self.reference_ranges: List[Dict[str, Any]] = []
        self.cuts_info: List[Dict[str, Any]] = []
        self.corrections: List[Dict[str, Any]] = []
        
        # Graph nodes and edges
        self.nodes: Set[Tuple[str, ...]] = set()
        self.edges: Set[Tuple[Tuple[str, ...], Tuple[str, ...], str]] = set()

    def _resolve_data_dir(self, path_str: str) -> Path:
        """Resolves the actual folder containing study CSV files."""
        candidate = Path(path_str)
        if (candidate / "data").is_dir() and (candidate / "data" / "DM.csv").is_file():
            return candidate / "data"
        if (candidate / "DM.csv").is_file():
            return candidate
            
        # Recursive search in case nested directory structure was provided
        for root, _, files in os.walk(candidate):
            if "DM.csv" in files and "LB.csv" in files:
                return Path(root)
                
        return candidate

    def _safe_int(self, val: Any, default: Optional[int] = None) -> Optional[int]:
        """Safely parse an integer, returning default if invalid or empty."""
        if val is None:
            return default
        val_str = str(val).strip()
        if not val_str:
            return default
        try:
            return int(val_str)
        except (ValueError, TypeError):
            try:
                return int(float(val_str))
            except (ValueError, TypeError):
                return default

    def _read_csv(self, filename: str) -> List[Dict[str, str]]:
        """Reads a CSV file with robust error handling for missing/malformed fields."""
        filepath = self.data_dir / filename
        if not filepath.is_file():
            return []

        rows: List[Dict[str, str]] = []
        with open(filepath, mode="r", encoding="utf-8-sig", errors="replace") as f:
            reader = csv.reader(f)
            try:
                header = next(reader, None)
            except Exception as e:
                logger.warning("Failed to read header from %s: %s", filename, e)
                return []

            if not header:
                return []

            cleaned_header = [col.strip() for col in header]

            for raw_row in reader:
                if not raw_row:
                    continue  # Skip empty line
                if len(raw_row) < len(cleaned_header):
                    raw_row = raw_row + [""] * (len(cleaned_header) - len(raw_row))
                elif len(raw_row) > len(cleaned_header):
                    raw_row = raw_row[:len(cleaned_header)]

                record = {cleaned_header[i]: raw_row[i].strip() for i in range(len(cleaned_header))}
                rows.append(record)

        return rows

    def _extract_seq(self, domain: str, row: Dict[str, str], auto_seq: int) -> int:
        """Extracts sequence number for a domain record."""
        seq_col = f"{domain}SEQ"
        if seq_col in row and row[seq_col]:
            parsed = self._safe_int(row[seq_col])
            if parsed is not None:
                return parsed

        for col in ("seq", "SEQ", "Sequence"):
            if col in row and row[col]:
                parsed = self._safe_int(row[col])
                if parsed is not None:
                    return parsed

        return auto_seq

    def build(self, cut: Optional[int] = None) -> Dict[str, Any]:
        """Loads and builds the study graph up to a specific data cut.
        
        Args:
            cut: Cut number (1 to 12). If None, all available records are loaded.
            
        Returns:
            Dictionary containing build statistics: nodes, edges, subjects, ms.
        """
        start_time = time.perf_counter()
        self.cut = cut
        
        # Reset state
        self.records_by_ref.clear()
        self.subjects.clear()
        self.subject_domain_records.clear()
        self.subject_visits.clear()
        self.nodes.clear()
        self.edges.clear()

        # 1. Load auxiliary data
        self.cuts_info = self._read_csv("cuts.csv")
        self.reference_ranges = self._read_csv("reference_ranges.csv")
        raw_corrections = self._read_csv("corrections.csv")
        
        parsed_corrections = []
        for corr in raw_corrections:
            c_cut = self._safe_int(corr.get("cut"))
            c_seq = self._safe_int(corr.get("seq"))
            if c_cut is not None and c_seq is not None:
                parsed_corrections.append({
                    "cut": c_cut,
                    "domain": corr.get("domain", "").upper(),
                    "usubjid": corr.get("usubjid", "").strip(),
                    "seq": c_seq,
                    "field": corr.get("field", "").strip(),
                    "old_value": corr.get("old_value", ""),
                    "new_value": corr.get("new_value", ""),
                    "reason": corr.get("reason", "")
                })
        self.corrections = parsed_corrections

        # 2. Load Demographics (DM.csv)
        dm_rows = self._read_csv("DM.csv")
        for row in dm_rows:
            usubjid = row.get("USUBJID", "").strip()
            if not usubjid:
                continue

            cut_avail = self._safe_int(row.get("cut_available"), 1)
            if cut is not None and cut_avail is not None and cut_avail > cut:
                continue

            site_id = row.get("SITEID", "").strip()
            if not site_id and "-" in usubjid:
                parts = usubjid.split("-")
                if len(parts) >= 2:
                    site_id = parts[1]

            arm = row.get("ARM", "").strip()

            dm_record = dict(row)
            dm_record["domain"] = "DM"
            dm_record["usubjid"] = usubjid
            dm_record["seq"] = 1
            dm_record["cut_available"] = cut_avail

            self.subjects[usubjid] = {
                "usubjid": usubjid,
                "site_id": site_id,
                "arm": arm,
                "demographics": row,
                "cut_available": cut_avail,
            }
            self.records_by_ref[("DM", usubjid, 1)] = dm_record
            self.subject_domain_records[(usubjid, "DM")] = [dm_record]

            subj_node = ("Subject", usubjid)
            self.nodes.add(subj_node)
            if site_id:
                site_node = ("Site", site_id)
                self.nodes.add(site_node)
                self.edges.add((site_node, subj_node, "ENROLLED"))

            dm_node = ("Record", "DM", usubjid, 1)
            self.nodes.add(dm_node)
            self.edges.add((subj_node, dm_node, "HAS_RECORD"))

        # 3. Load all other domain files
        other_domains = [d for d in self.KNOWN_DOMAINS if d != "DM"]
        for domain in other_domains:
            csv_file = f"{domain}.csv"
            raw_rows = self._read_csv(csv_file)
            auto_seq_counter: Dict[str, int] = {}

            for row in raw_rows:
                usubjid = row.get("USUBJID", "").strip()
                if not usubjid:
                    continue

                cut_avail = self._safe_int(row.get("cut_available"), 1)
                if cut is not None and cut_avail is not None and cut_avail > cut:
                    continue

                auto_seq_counter[usubjid] = auto_seq_counter.get(usubjid, 0) + 1
                seq = self._extract_seq(domain, row, auto_seq_counter[usubjid])

                if usubjid not in self.subjects:
                    site_id = ""
                    if "-" in usubjid:
                        parts = usubjid.split("-")
                        if len(parts) >= 2:
                            site_id = parts[1]
                    self.subjects[usubjid] = {
                        "usubjid": usubjid,
                        "site_id": site_id,
                        "arm": "",
                        "demographics": {},
                        "cut_available": cut_avail,
                    }
                    subj_node = ("Subject", usubjid)
                    self.nodes.add(subj_node)
                    if site_id:
                        site_node = ("Site", site_id)
                        self.nodes.add(site_node)
                        self.edges.add((site_node, subj_node, "ENROLLED"))

                record = dict(row)
                record["domain"] = domain
                record["usubjid"] = usubjid
                record["seq"] = seq
                record["cut_available"] = cut_avail

                ref_key = (domain, usubjid, seq)
                self.records_by_ref[ref_key] = record

                sub_dom_key = (usubjid, domain)
                if sub_dom_key not in self.subject_domain_records:
                    self.subject_domain_records[sub_dom_key] = []
                self.subject_domain_records[sub_dom_key].append(record)

                visit = row.get("VISIT", "").strip()
                if usubjid not in self.subject_visits:
                    self.subject_visits[usubjid] = {}

                subj_node = ("Subject", usubjid)
                rec_node = ("Record", domain, usubjid, seq)
                self.nodes.add(rec_node)

                if visit:
                    if visit not in self.subject_visits[usubjid]:
                        self.subject_visits[usubjid][visit] = []
                    self.subject_visits[usubjid][visit].append(record)

                    visit_node = ("Visit", usubjid, visit)
                    self.nodes.add(visit_node)
                    self.edges.add((subj_node, visit_node, "HAD_VISIT"))
                    self.edges.add((visit_node, rec_node, "CONTAINS_RECORD"))
                else:
                    self.edges.add((subj_node, rec_node, "HAS_RECORD"))

        # 4. Apply corrections up to current cut
        for corr in self.corrections:
            if cut is not None and corr["cut"] > cut:
                continue

            ref_key = (corr["domain"], corr["usubjid"], corr["seq"])
            if ref_key in self.records_by_ref:
                target_rec = self.records_by_ref[ref_key]
                field = corr["field"]
                target_rec[f"_orig_{field}"] = target_rec.get(field, corr["old_value"])
                target_rec[field] = corr["new_value"]
                target_rec["_corrected"] = True
                target_rec["_correction_cut"] = corr["cut"]

        elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

        stats = {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "subjects": len(self.subjects),
            "subjects_covered": len(self.subjects),
            "cut": cut,
            "build_time_ms": elapsed_ms,
            "ms": elapsed_ms,
        }
        return stats

    def patient360(self, usubjid: str) -> Dict[str, Any]:
        """Returns the connected representation of all records for a subject."""
        subj = self.subjects.get(usubjid)
        if not subj:
            return {"usubjid": usubjid, "records": []}

        records_by_domain: Dict[str, List[Dict[str, Any]]] = {}
        all_records: List[Dict[str, Any]] = []

        for domain in self.KNOWN_DOMAINS:
            dom_records = self.subject_domain_records.get((usubjid, domain), [])
            records_by_domain[domain] = list(dom_records)
            all_records.extend(dom_records)

        visits = {v: list(recs) for v, recs in self.subject_visits.get(usubjid, {}).items()}

        return {
            "usubjid": usubjid,
            "site_id": subj.get("site_id", ""),
            "arm": subj.get("arm", ""),
            "demographics": subj.get("demographics", {}),
            "records_by_domain": records_by_domain,
            "visits": visits,
            "records": all_records,
        }

    def get_record(self, domain: str, usubjid: str, seq: int) -> Optional[Dict[str, Any]]:
        """O(1) record retrieval for evidence verification by (domain, usubjid, seq)."""
        return self.records_by_ref.get((domain.upper(), usubjid, seq))


class Atlas:
    """Stage 1 Question-Answering Agent for Study Sentinel.
    
    Parses reviewer queries into deterministic clinical checks, applies protocol rules,
    and returns exact answers backed by verified RecordRefs.
    """

    def __init__(self, graph: StudyGraph, rules: Optional[ProtocolRules] = None):
        self.graph = graph
        self._explicit_rules = rules
        self.clinical = ClinicalReasoning(graph, rules)
        self.validator = EvidenceValidator(graph)

    @property
    def rules(self) -> ProtocolRules:
        if self._explicit_rules is not None:
            return self._explicit_rules
        return ProtocolRules.for_cut(getattr(self.graph, "cut", None))

    def answer(self, question: Union[Question, Dict[str, Any]]) -> Answer:
        """Answers a clinical query citing verified record evidence.
        
        Supports all four question categories:
        - count: integer answers with supporting records
        - lookup: lists of record references within specified windows
        - finding: candidate subject IDs backed by laboratory or safety records
        - trap: returns [] when nothing meets criteria, without inventing evidence
        """
        # 1. Unpack Question
        if isinstance(question, Question):
            qid = question.question_id
            text = question.text
            kind = question.kind
        elif isinstance(question, dict):
            qid = question.get("question_id", "Q000")
            text = question.get("text", "")
            kind = question.get("kind")
        else:
            qid = getattr(question, "question_id", "Q000")
            text = getattr(question, "text", str(question))
            kind = getattr(question, "kind", None)

        text_lower = text.lower()

        # 2. Extract Entities
        site_match = re.search(r"\b(s\d{2})\b", text, re.IGNORECASE)
        site_filter = site_match.group(1).upper() if site_match else None

        subj_match = re.search(r"\b(\d{3}-s\d{2}-\d{3})\b", text, re.IGNORECASE)
        subj_filter = subj_match.group(1) if subj_match else None

        visit_match = re.search(r"\b(screening|baseline|week\s*\d+|end\s+of\s+study|eos)\b", text, re.IGNORECASE)
        visit_filter = visit_match.group(1).upper().replace(" ", "") if visit_match else None

        window_match = re.search(r"within\s+(\d+)\s+days", text, re.IGNORECASE)
        window_days = int(window_match.group(1)) if window_match else 7

        is_count_query = (
            kind == "count"
            or text_lower.startswith("how many")
            or "count of" in text_lower
            or "number of" in text_lower
        )

        steps_used = 2

        # 3. Deterministic Clinical Operation Selection
        # A. Hy's Law / Liver Safety
        if "hy's law" in text_lower or "hys law" in text_lower or "liver" in text_lower:
            steps_used = 6
            res = self.clinical.detect_hys_law_candidates(
                site_filter=site_filter,
                subject_filter=subj_filter
            )
            candidates = res["candidates"]
            if is_count_query:
                ans_val: Any = len(candidates)
            else:
                ans_val = candidates

            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # B. Dosing Deviations / Wrong Dose
        elif "dose" in text_lower or "dosing" in text_lower:
            steps_used = 4
            res = self.clinical.detect_dosing_errors(site_filter=site_filter)
            err_subjs = res["subjects"]
            if is_count_query:
                ans_val = res["count"]
            else:
                ans_val = err_subjs

            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # C. Discontinuations due to Adverse Events
        elif "discontinu" in text_lower and ("adverse" in text_lower or "ae" in text_lower):
            steps_used = 4
            res = self.clinical.detect_discontinuations_by_ae(site_filter=site_filter)
            disc_subjs = res["subjects"]
            if is_count_query:
                ans_val = res["count"]
            else:
                ans_val = disc_subjs

            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # D. Prohibited Concomitant Medications
        elif "prohibited" in text_lower or "medication" in text_lower or "concomitant" in text_lower or "sulfonylurea" in text_lower or "glucocorticoid" in text_lower:
            steps_used = 4
            res = self.clinical.detect_prohibited_medications(site_filter=site_filter)
            violators = res["subjects"]
            if is_count_query:
                ans_val = res["count"]
            else:
                ans_val = violators

            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # E. Serious Adverse Events / Hospitalization
        elif "serious" in text_lower or "hospital" in text_lower:
            steps_used = 4
            res = self.clinical.detect_serious_adverse_events(site_filter=site_filter)
            sae_subjs = res["subjects"]
            if is_count_query:
                ans_val = res["count"]
            else:
                ans_val = sae_subjs

            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # F. Lookup of records near visit
        elif (
            ("list" in text_lower or "find" in text_lower or "lookup" in text_lower or kind == "lookup")
            and subj_filter
            and visit_filter
        ):
            steps_used = 5
            target_domains = []
            if "lab" in text_lower or "laboratory" in text_lower:
                target_domains.append("LB")
            if "adverse" in text_lower or "ae" in text_lower:
                target_domains.append("AE")
            if "dose" in text_lower or "exposure" in text_lower:
                target_domains.append("EX")
            if not target_domains:
                target_domains = ["LB", "AE"]

            res = self.clinical.lookup_records_near_visit(
                usubjid=subj_filter,
                visit_name=visit_filter,
                window_days=window_days,
                domains=target_domains,
            )
            ans_val = res["answer"]
            ans_text = res["text"]
            raw_evidence = res["evidence"]
            confidence = res["confidence"]

        # G. General Count / Discontinuation query
        elif is_count_query and "subject" in text_lower:
            steps_used = 3
            matched_subjs = []
            for sub, sdata in self.graph.subjects.items():
                if site_filter and sdata.get("site_id") != site_filter:
                    continue
                matched_subjs.append(sub)
            ans_val = len(matched_subjs)
            ans_text = f"{len(matched_subjs)} subjects at site {site_filter or 'all sites'}."
            raw_evidence = [{"domain": "DM", "usubjid": s, "seq": 1} for s in matched_subjs]
            confidence = 0.95

        # H. Honest Trap / Fallback
        else:
            steps_used = 2
            ans_val = []
            ans_text = "No records or criteria match the requested query."
            raw_evidence = []
            confidence = 0.85

        # 4. Evidence Validation & Deduplication
        verified_evidence = self.validator.validate_and_deduplicate(raw_evidence)

        # 5. Return Validated Answer Schema
        return Answer(
            question_id=qid,
            answer=ans_val,
            text=ans_text,
            evidence=verified_evidence,
            confidence=confidence,
            steps_used=steps_used,
            tokens_used=0,
        )


def main():
    """CLI entrypoint for running Stage 1 - ATLAS."""
    parser = argparse.ArgumentParser(description="Stage 1 - ATLAS StudyGraph & Answer Engine")
    parser.add_argument("--data", type=str, required=True, help="Path to study data directory")
    parser.add_argument("--cut", type=int, default=None, help="Data cut to build (1 to 12)")
    parser.add_argument("--output-stats", type=str, default="graph_stats.json", help="Path to output build stats")
    parser.add_argument("--output-answers", type=str, default="stage1_public.json", help="Path to output public answers")
    args = parser.parse_args()

    print(f"Loading StudyGraph from: {args.data} (Cut: {args.cut})")
    graph = StudyGraph(args.data)
    stats = graph.build(args.cut)
    print(f"Graph built successfully in {stats['build_time_ms']} ms:")
    print(f"  Nodes: {stats['nodes']}")
    print(f"  Edges: {stats['edges']}")
    print(f"  Subjects: {stats['subjects']}")

    with open(args.output_stats, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"Saved build statistics to {args.output_stats}")

    # Standard public test question suite
    public_questions = [
        Question("Q001", "How many subjects at site S07 discontinued due to an adverse event?", kind="count"),
        Question("Q002", "How many subjects at site S11 discontinued due to an adverse event?", kind="count"),
        Question("Q003", "List the laboratory and adverse-event records for 042-S05-003 within 7 days of the WEEK8 visit", kind="lookup"),
        Question("Q004", "Which subjects meet potential Hy's law criteria?", kind="finding"),
        Question("Q005", "Which subjects at site S07 meet potential Hy's law criteria?", kind="finding"),
        Question("Q006", "Which subjects at site S01 received a wrong dose?", kind="trap"),
        Question("Q007", "Which subjects at site S09 received a wrong dose?", kind="finding"),
        Question("Q008", "Which subjects took prohibited concomitant medications?", kind="finding"),
        Question("Q009", "Which subjects at site S05 have serious adverse events?", kind="finding"),
        Question("Q010", "Which subjects at site S02 received a wrong dose?", kind="trap"),
    ]

    atlas = Atlas(graph)
    answers = []
    print("\nAnswering public questions:")
    for q in public_questions:
        ans = atlas.answer(q)
        ans_dict = ans.to_dict()
        answers.append(ans_dict)
        print(f"  [{q.question_id}] Answer: {ans.answer} | Evidence count: {len(ans.evidence)}")

    with open(args.output_answers, "w", encoding="utf-8") as f:
        json.dump(answers, f, indent=2)
    print(f"Saved public answers to {args.output_answers}")


if __name__ == "__main__":
    main()
