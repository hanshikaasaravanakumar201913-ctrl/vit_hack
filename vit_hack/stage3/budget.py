"""ATLAS Stage 3 — Global Processing Budget & Graceful Degradation Manager.

Tracks time and compute resource consumption across the 12 cuts.
Transitions gracefully across HEALTHY, LIMITED, and CRITICAL states.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional
from stage3.models import BudgetState

logger = logging.getLogger("atlas.stage3.budget")


class BudgetManager:
    """Manages study processing time budget and enforces graceful degradation."""

    def __init__(
        self,
        total_seconds: float = 120.0,
        max_operations: int = 100000,
    ) -> None:
        self.total_seconds = total_seconds
        self.max_operations = max_operations
        self.start_time: float = time.perf_counter()
        self.operations_count: int = 0
        self.degraded_steps: int = 0

    def reset(self) -> None:
        self.start_time = time.perf_counter()
        self.operations_count = 0
        self.degraded_steps = 0

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.start_time

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, self.total_seconds - self.elapsed_seconds)

    @property
    def remaining_fraction(self) -> float:
        if self.total_seconds <= 0:
            return 1.0
        return max(0.0, min(1.0, self.remaining_seconds / self.total_seconds))

    def get_state(self) -> BudgetState:
        """Computes current budget state based on elapsed time and operation load."""
        frac = self.remaining_fraction
        if frac > 0.30:
            return BudgetState.HEALTHY
        elif frac > 0.10:
            return BudgetState.LIMITED
        else:
            return BudgetState.CRITICAL

    def record_step(self, count: int = 1) -> None:
        self.operations_count += count

    def should_skip_nonessential(self) -> bool:
        """Whether to skip expensive narrative re-generation or non-critical deep scans."""
        st = self.get_state()
        if st in (BudgetState.LIMITED, BudgetState.CRITICAL):
            self.degraded_steps += 1
            return True
        return False

    def should_halt_non_safety(self) -> bool:
        """Whether to strictly halt everything except mandatory safety checks (Hy's law, SAEs)."""
        st = self.get_state()
        if st == BudgetState.CRITICAL:
            self.degraded_steps += 1
            return True
        return False

    def get_elapsed_seconds(self) -> float:
        return round(self.elapsed_seconds, 2)

    def get_remaining_seconds(self) -> float:
        return round(self.remaining_seconds, 2)

    @property
    def records_processed(self) -> int:
        return self.operations_count

    def get_degradation_profile(self) -> Dict[str, Any]:
        state = self.get_state()
        if state == BudgetState.HEALTHY:
            return {
                "state": "HEALTHY",
                "action": "FULL_PROCESSING",
                "narratives_enabled": True,
                "deep_scan_enabled": True,
                "safety_checks_enabled": True,
            }
        elif state == BudgetState.LIMITED:
            return {
                "state": "LIMITED",
                "action": "SKIP_NONESSENTIAL_NARRATIVES",
                "narratives_enabled": False,
                "deep_scan_enabled": True,
                "safety_checks_enabled": True,
            }
        else:
            return {
                "state": "CRITICAL",
                "action": "SAFETY_CHECKS_ONLY",
                "narratives_enabled": False,
                "deep_scan_enabled": False,
                "safety_checks_enabled": True,
            }

    def get_status_dict(self) -> Dict[str, Any]:
        return {
            "total_budget_s": self.total_seconds,
            "elapsed_s": round(self.elapsed_seconds, 2),
            "remaining_s": round(self.remaining_seconds, 2),
            "remaining_pct": round(self.remaining_fraction * 100, 1),
            "state": self.get_state().value,
            "operations_count": self.operations_count,
            "degraded_steps": self.degraded_steps,
            "degradation_profile": self.get_degradation_profile(),
        }
