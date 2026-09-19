"""ATLAS Stage 2 — MONITOR Longitudinal Review Memory.

Maintains state across review cycles to support:
- Query deduplication (no redundant queries to sites)
- Escalation deduplication (prevent re-escalation of active issues)
- Rejection persistence (rejected items remain monitoring-only, never re-escalated)
- Repeated subject tracking across cycles (>= 2 distinct cuts triggers repeated escalation)
- Site clustering (tracking patterns per investigational site)
"""

from __future__ import annotations

from typing import Any, Dict, List, Set
from stage2.models import Escalation, GateDecision, SiteQuery


class ReviewMemory:
    """Longitudinal state repository across ReviewCrew cycles."""

    def __init__(self) -> None:
        # Map of query key ("DOMAIN|USUBJID|SEQ") -> SiteQuery
        self.queries: Dict[str, SiteQuery] = {}
        
        # Map of escalation key ("FINDING_CODE|TARGET_ID") -> Escalation
        self.escalations: Dict[str, Escalation] = {}
        
        # Set of escalation keys rejected by the human monitor
        # CRITICAL RULE: Rejection persists forever; items remain monitoring-only and NEVER re-escalate
        self.rejected_items: Set[str] = set()
        
        # History of findings per subject across cuts: usubjid -> set of cut numbers
        self.subject_cuts: Dict[str, Set[int]] = {}
        
        # History of findings per subject across cycles: usubjid -> set of cycle numbers
        self.subject_cycles: Dict[str, Set[int]] = {}
        
        # Map of site_id -> list of deviation/error finding IDs
        self.site_deviations: Dict[str, List[str]] = {}

        # Set of escalated repeated subjects to prevent duplicate repeated escalations
        self.escalated_repeated_subjects: Set[str] = set()

        # Set of escalated site clusters to prevent duplicate site cluster escalations
        self.escalated_site_clusters: Set[str] = set()

        # Last processed cut
        self.last_cut: int | None = None

    def is_query_already_raised(self, key: str) -> bool:
        """Checks if a data management query on this record was already raised in a previous cycle."""
        return key in self.queries

    def record_query(self, query: SiteQuery) -> None:
        """Saves a raised query to memory."""
        self.queries[query.key] = query

    def is_item_rejected(self, key: str) -> bool:
        """Checks if this finding was previously rejected by the medical monitor."""
        return key in self.rejected_items

    def record_rejection(self, key: str) -> None:
        """Permanently records an escalation rejection. Persists across all future cycles."""
        self.rejected_items.add(key)

    def is_escalation_active(self, key: str) -> bool:
        """Checks if an escalation for this key was already created and not rejected."""
        if key in self.rejected_items:
            return False
        return key in self.escalations

    def record_escalation(self, escalation: Escalation) -> None:
        """Saves an escalation to memory."""
        self.escalations[escalation.key] = escalation

    def record_subject_finding(self, usubjid: str, cycle: int, cut: int) -> None:
        """Records that a subject had a finding in the specified review cycle and cut."""
        if usubjid not in self.subject_cuts:
            self.subject_cuts[usubjid] = set()
        self.subject_cuts[usubjid].add(cut)

        if usubjid not in self.subject_cycles:
            self.subject_cycles[usubjid] = set()
        self.subject_cycles[usubjid].add(cycle)

    def get_repeated_subjects(self, min_cuts: int = 2) -> List[str]:
        """Identifies subjects with findings across min_cuts or more distinct data cuts."""
        repeated = []
        for usubjid, cuts in self.subject_cuts.items():
            if len(cuts) >= min_cuts and usubjid not in self.escalated_repeated_subjects:
                repeated.append(usubjid)
        return sorted(repeated)

    def record_site_deviation(self, site_id: str, finding_id: str) -> None:
        """Tracks deviation occurrences per site."""
        if site_id not in self.site_deviations:
            self.site_deviations[site_id] = []
        self.site_deviations[site_id].append(finding_id)

    def get_site_cluster_sites(self, threshold: int = 3) -> List[str]:
        """Identifies sites with >= threshold deviations that haven't been cluster-escalated."""
        clusters = []
        for site_id, dev_ids in self.site_deviations.items():
            if len(dev_ids) >= threshold and site_id not in self.escalated_site_clusters:
                clusters.append(site_id)
        return sorted(clusters)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_queries": len(self.queries),
            "total_escalations": len(self.escalations),
            "rejected_items_count": len(self.rejected_items),
            "rejected_items": sorted(list(self.rejected_items)),
            "subject_cuts_tracked": len(self.subject_cuts),
            "site_deviations_tracked": {s: len(d) for s, d in self.site_deviations.items()},
        }
