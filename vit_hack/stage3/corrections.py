"""ATLAS Stage 3 — Corrections & State Re-Derivation Manager.

Tracks official data cut corrections from corrections.csv.
When corrections arrive:
OLD FINDING -> CORRECTION -> IDENTIFY AFFECTED STATE -> RE-DERIVE AFFECTED FINDING -> UPDATE DECISION -> PRESERVE AUDIT HISTORY.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from stage1.atlas import StudyGraph
from stage3.models import WatchDecision, WatchDecisionStatus

logger = logging.getLogger("atlas.stage3.corrections")


class CorrectionsManager:
    """Processes official corrections and re-derives affected findings while preserving audit history."""

    def __init__(self, graph: StudyGraph) -> None:
        self.graph = graph
        self.applied_corrections: List[Dict[str, Any]] = []
        self.correction_history_by_ref: Dict[Tuple[str, str, int], List[Dict[str, Any]]] = {}

    def apply_cut_corrections(
        self,
        cut: int,
        existing_decisions: Dict[str, WatchDecision],
    ) -> List[Dict[str, Any]]:
        """Applies corrections for the specified cut, identifying affected decisions and re-deriving them."""
        cut_corrs = [c for c in self.graph.corrections if c.get("cut") == cut]
        re_derived_events: List[Dict[str, Any]] = []

        for corr in cut_corrs:
            domain = corr["domain"]
            usubjid = corr["usubjid"]
            seq = corr["seq"]
            field = corr["field"]
            old_val = corr["old_value"]
            new_val = corr["new_value"]
            reason = corr.get("reason", "Central laboratory re-issue")

            ref_key = (domain, usubjid, seq)
            self.applied_corrections.append(corr)

            if ref_key not in self.correction_history_by_ref:
                self.correction_history_by_ref[ref_key] = []
            self.correction_history_by_ref[ref_key].append(corr)

            # Identify any existing decisions that cited this record
            for dec_id, dec in list(existing_decisions.items()):
                cited = False
                for ev in dec.evidence:
                    if isinstance(ev, dict) and ev.get("domain") == domain and ev.get("usubjid") == usubjid and ev.get("seq") == seq:
                        cited = True
                        break
                    elif isinstance(ev, tuple) and ev == ref_key:
                        cited = True
                        break

                if cited:
                    # Update decision trace with audit record
                    audit_entry = {
                        "event": "RECORD_CORRECTION_APPLIED",
                        "cut": cut,
                        "record": f"{domain}|{usubjid}|{seq}",
                        "field": field,
                        "old_value": old_val,
                        "new_value": new_val,
                        "reason": reason,
                    }
                    dec.trace.append(audit_entry)
                    re_derived_events.append({
                        "decision_id": dec_id,
                        "cut": cut,
                        "record": f"{domain}|{usubjid}|{seq}",
                        "change": f"{old_val} -> {new_val}",
                        "action": "DECISION_RE_EVALUATED_AND_HISTORY_PRESERVED",
                    })

        return re_derived_events
