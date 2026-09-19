"""ATLAS Stage 2 — MONITOR Immutable Structured Audit Trail.

Records deterministic, timestamped execution events for all 6 ReviewCrew nodes.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List
from stage2.models import TraceEntry


class AuditTrace:
    """In-memory append-only structured audit trail."""

    def __init__(self) -> None:
        self._entries: List[TraceEntry] = []

    def record_step(
        self,
        cycle: int,
        node: str,
        action: str,
        input_summary: Dict[str, Any] | None = None,
        output_summary: Dict[str, Any] | None = None,
        details: Dict[str, Any] | None = None,
    ) -> TraceEntry:
        """Appends a new trace entry to the immutable log."""
        entry_id = f"TRC-{cycle:03d}-{len(self._entries) + 1:04d}"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        entry = TraceEntry(
            entry_id=entry_id,
            cycle=cycle,
            node=node,
            timestamp=now_ts,
            action=action,
            input_summary=input_summary or {},
            output_summary=output_summary or {},
            details=details or {},
        )
        self._entries.append(entry)
        return entry

    def get_entries(self) -> List[TraceEntry]:
        """Returns all trace entries in chronological order."""
        return list(self._entries)

    def get_cycle_entries(self, cycle: int) -> List[TraceEntry]:
        """Returns all trace entries recorded during a specific cycle."""
        return [e for e in self._entries if e.cycle == cycle]

    def clear(self) -> None:
        """Clears trace log (for testing only)."""
        self._entries.clear()

    def to_list(self) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._entries]
