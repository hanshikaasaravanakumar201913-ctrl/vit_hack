"""ATLAS Stage 2 — MONITOR Gateway Interface.

Interacts with simulated human monitor responses and site query replies:
- monitor_decisions.json (APPROVED, REJECTED, CLARIFY)
- site_replies.json (CLOSED, ANSWERED)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("atlas.stage2.gateway")


class MonitorGateway:
    """Gateway client interfacing with monitor decisions and site query responses."""

    def __init__(self, responses_dir: Optional[Path] = None) -> None:
        self.responses_dir = responses_dir
        self.monitor_decisions: Dict[str, Any] = {}
        self.site_replies: Dict[str, Any] = {}
        self.default_site_reply: Tuple[str, str] = ("ANSWERED", "Data verified against source documents. No change.")

        if self.responses_dir and self.responses_dir.exists():
            self._load_local_responses()

    def _load_local_responses(self) -> None:
        """Loads scripted monitor decisions and site replies from disk."""
        if not self.responses_dir:
            return

        dec_file = self.responses_dir / "monitor_decisions.json"
        if dec_file.exists():
            try:
                with open(dec_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.monitor_decisions = raw.get("decisions", {})
                logger.info("Loaded %d monitor decisions from %s", len(self.monitor_decisions), dec_file.name)
            except Exception as e:
                logger.error("Failed loading monitor_decisions.json: %s", e)

        rep_file = self.responses_dir / "site_replies.json"
        if rep_file.exists():
            try:
                with open(rep_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.site_replies = raw.get("replies", {})
                    def_rep = raw.get("_default")
                    if def_rep and isinstance(def_rep, list) and len(def_rep) >= 2:
                        self.default_site_reply = (def_rep[0], def_rep[1])
                logger.info("Loaded %d site replies from %s", len(self.site_replies), rep_file.name)
            except Exception as e:
                logger.error("Failed loading site_replies.json: %s", e)

    def get_monitor_decision(self, finding_code: str, target_id: str) -> Tuple[str, str]:
        """Queries the medical monitor for a decision on an escalation.
        
        Lookup format: 'FINDING_CODE|USUBJID' or 'FINDING_CODE|SITEID'
        Returns: (decision, reason), e.g. ('APPROVED', 'Serious adverse event confirmed...')
        """
        key = f"{finding_code}|{target_id}"
        if key in self.monitor_decisions:
            val = self.monitor_decisions[key]
            if isinstance(val, list) and len(val) >= 2:
                return (val[0], val[1])
            elif isinstance(val, list) and len(val) == 1:
                return (val[0], "")
        
        # Check site ID fallback if target_id is USUBJID (e.g. 042-S01-001 -> S01)
        if "-S" in target_id:
            parts = target_id.split("-")
            if len(parts) >= 2:
                site_key = f"{finding_code}|{parts[1]}"
                if site_key in self.monitor_decisions:
                    val = self.monitor_decisions[site_key]
                    if isinstance(val, list) and len(val) >= 2:
                        return (val[0], val[1])

        # Default fallback for unscripted items
        return ("APPROVED", "Reviewed and accepted by medical monitor.")

    def get_site_reply(self, domain: str, usubjid: str, seq: int) -> Tuple[str, str]:
        """Queries the clinical site for an answer to a data management query.
        
        Lookup format: 'DOMAIN|USUBJID|SEQ'
        Returns: (status, comment), e.g. ('CLOSED', 'Date entry error confirmed...')
        """
        key = f"{domain}|{usubjid}|{seq}"
        if key in self.site_replies:
            val = self.site_replies[key]
            if isinstance(val, list) and len(val) >= 2:
                return (val[0], val[1])
            elif isinstance(val, list) and len(val) == 1:
                return (val[0], "")
        
        return self.default_site_reply
