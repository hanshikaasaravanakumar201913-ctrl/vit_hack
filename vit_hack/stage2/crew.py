"""ATLAS Stage 2 — MONITOR ReviewCrew Coordinator.

Orchestrates the 6 deterministic review nodes:
detect -> medical_review -> data_manager -> compliance -> human_gate -> execute.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from stage1.atlas import Atlas
from stage2.gateway import MonitorGateway
from stage2.memory import ReviewMemory
from stage2.models import ReviewReport
from stage2.nodes import (
    CrewContext,
    run_compliance,
    run_data_manager,
    run_detect,
    run_execute,
    run_human_gate,
    run_medical_review,
)
from stage2.trace import AuditTrace

logger = logging.getLogger("atlas.stage2.crew")


class ReviewCrew:
    """Deterministic 6-Node Multi-Agent Clinical Review Crew."""

    def __init__(
        self,
        hub_url: str = "http://localhost:8080",
        gateway_url: str = "http://localhost:8080",
        team_key: str = "ATLAS-TEAM-2026",
        atlas: Optional[Atlas] = None,
        responses_dir: Optional[Path] = None,
    ) -> None:
        self.hub_url = hub_url
        self.gateway_url = gateway_url
        self.team_key = team_key
        
        # In-memory shared dependencies
        if atlas is not None:
            self.atlas = atlas
        else:
            # Fallback initialization if none provided
            self.atlas = Atlas()

        # Responses directory for Gateway decisions & replies
        if responses_dir is None:
            candidates = []
            if hasattr(self.atlas.graph, "raw_data_dir") and self.atlas.graph.raw_data_dir:
                candidates.append(Path(self.atlas.graph.raw_data_dir) / "responses")
            if hasattr(self.atlas.graph, "data_dir") and self.atlas.graph.data_dir:
                candidates.append(Path(self.atlas.graph.data_dir) / "responses")
                candidates.append(Path(self.atlas.graph.data_dir).parent / "responses")
            candidates.append(Path("DATASET-20260918T152607Z-1-001/DATASET/hackathon-data/hackathon-data/responses"))
            for c in candidates:
                if c.exists():
                    responses_dir = c
                    break

        self.gateway = MonitorGateway(responses_dir=responses_dir)
        self.memory = ReviewMemory()
        self.trace = AuditTrace()
        self.cycle_count = 0
        self.reports: list[ReviewReport] = []

    def run_cycle(self, cut: int = 12, protocol_version: int = 3) -> ReviewReport:
        """Executes a complete 6-node review cycle against the specified cut and protocol version."""
        self.cycle_count += 1
        cycle = self.cycle_count

        logger.info("Starting ReviewCrew Cycle %d (Cut: %d, Protocol v%d)...", cycle, cut, protocol_version)

        # 1. Update Atlas graph cut & rules if cut changed
        if self.atlas.graph.cut != cut:
            self.atlas.graph.build(cut=cut)
        self.atlas.rules.protocol_version = protocol_version

        # 2. Build Cycle Context
        ctx = CrewContext(
            cycle=cycle,
            cut=cut,
            protocol_version=protocol_version,
            atlas=self.atlas,
            gateway=self.gateway,
            memory=self.memory,
            trace=self.trace,
        )

        # 3. Execute the 6 nodes in strict deterministic sequence
        # Node 1: Detect
        run_detect(ctx)

        # Node 2: Medical Review
        run_medical_review(ctx)

        # Node 3: Data Manager
        run_data_manager(ctx)

        # Node 4: Compliance
        run_compliance(ctx)

        # Node 5: Human Gate
        run_human_gate(ctx)

        # Node 6: Execute
        run_execute(ctx)

        if ctx.report is None:
            raise RuntimeError(f"ReviewCrew Cycle {cycle} failed to produce a ReviewReport.")

        self.reports.append(ctx.report)
        logger.info("ReviewCrew Cycle %d finished successfully: %s", cycle, ctx.report.summary)
        return ctx.report

    def get_last_report(self) -> Optional[ReviewReport]:
        return self.reports[-1] if self.reports else None
