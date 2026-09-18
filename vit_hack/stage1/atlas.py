"""Stage 1 - ATLAS: StudyGraph data loading and representation layer.

This module implements the StudyGraph class responsible for loading, validating,
correcting, and indexing clinical trial records into an in-memory graph
and subject index (Patient 360).
"""

from __future__ import annotations

import csv
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

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

            for row_idx, raw_row in enumerate(reader, start=2):
                if not raw_row:
                    continue  # Skip empty line
                # Handle row with fewer columns than header by padding
                if len(raw_row) < len(cleaned_header):
                    raw_row = raw_row + [""] * (len(cleaned_header) - len(raw_row))
                # Handle row with more columns than header by slicing
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

        # Check alternative SEQ column names
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
        
        # Parse corrections
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

        # 2. Load Demographics (DM.csv) first to initialize subjects
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

            # Record Demographics as domain record with seq=1
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

            # Graph Nodes & Edges
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
                    continue  # Malformed row without subject ID

                cut_avail = self._safe_int(row.get("cut_available"), 1)
                if cut is not None and cut_avail is not None and cut_avail > cut:
                    continue

                auto_seq_counter[usubjid] = auto_seq_counter.get(usubjid, 0) + 1
                seq = self._extract_seq(domain, row, auto_seq_counter[usubjid])

                # Ensure subject exists even if DM record was missing
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

                # Group by subject and domain
                sub_dom_key = (usubjid, domain)
                if sub_dom_key not in self.subject_domain_records:
                    self.subject_domain_records[sub_dom_key] = []
                self.subject_domain_records[sub_dom_key].append(record)

                # Group by visit if applicable
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
        """Returns the connected representation of all records for a subject.
        
        Args:
            usubjid: Unique subject identifier (e.g. '042-S07-001').
            
        Returns:
            Dictionary containing demographics, records grouped by domain,
            records grouped by visit, and a complete flat list of all records.
        """
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
    """Atlas query engine stub for Stage 1.
    
    Deferred to the next architecture layer per instructions.
    """
    def __init__(self, graph: StudyGraph):
        self.graph = graph

    def answer(self, question: Any) -> Any:
        raise NotImplementedError("Atlas question answering is deferred to the next phase.")
