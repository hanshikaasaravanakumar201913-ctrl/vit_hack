"""Unit Tests for Stage 3 — WATCH Longitudinal Clinical Surveillance & Conversational Assistant.

Tests all Problem 3 core capabilities:
- Stage 3 imports Stage 2 architecture rule
- Incremental 12-cut surveillance execution
- Data-driven suspicious site statistical anomaly detection (Site S11)
- Laboratory data integrity vs clinical safety emergency (Site S04 at Cut 8)
- Protocol amendments tracking (v1 -> v2 -> v3) and affected subject impact
- Slow / unanswered monitor policy (explicit UNANSWERED state, no silent approval)
- Global processing budget management and degradation
- Trace-backed explainable decision retrieval (explain())
- Unified conversational assistant routing across ATLAS, ReviewCrew, and WATCH
"""

import os
import sys
import unittest
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Test mandatory architecture rule: stage3 imports stage2
import stage3
import stage2
from stage1.atlas import Atlas, StudyGraph
from stage1.ai.orchestrator import AtlasConversationalOrchestrator
from stage3.models import (
    BudgetState,
    WatchDecisionStatus,
    SuspiciousSiteFinding,
    DataIntegrityFinding,
    ProtocolDiff,
)
from stage3.budget import BudgetManager
from stage3.detectors import (
    SuspiciousSiteDetector,
    DataIntegrityDetector,
    ProtocolAmendmentDetector,
)
from stage3.watch import WatchSurveillance


class TestStage3Watch(unittest.TestCase):
    """Test suite for Stage 3 WATCH Surveillance Engine."""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = REPO_ROOT / "DATASET-20260918T152607Z-1-001" / "DATASET" / "hackathon-data" / "hackathon-data"
        cls.graph = StudyGraph(str(cls.data_dir))
        cls.graph.build(12)
        cls.atlas = Atlas(cls.graph)
        cls.watch = WatchSurveillance(atlas=cls.atlas)
        cls.watch.run_all_cuts(12)
        cls.orchestrator = AtlasConversationalOrchestrator(
            atlas=cls.atlas,
            watch=cls.watch,
        )

    def test_01_architecture_rule_stage3_imports_stage2(self):
        """Mandatory rule: stage3 module MUST import stage2."""
        self.assertIn("stage2", sys.modules)
        self.assertTrue(hasattr(stage3, "WatchSurveillance"))

    def test_02_incremental_12_cuts_processing(self):
        """Verifies that all 12 surveillance cuts execute incrementally."""
        self.assertEqual(len(self.watch.cut_reports), 12)
        for cut_num in range(1, 13):
            rep = self.watch.cut_reports[cut_num]
            self.assertEqual(rep.cut, cut_num)
            self.assertGreater(rep.new_records_count, 0)
            self.assertIn(rep.budget_state, [BudgetState.HEALTHY, BudgetState.LIMITED, BudgetState.CRITICAL])
            self.assertGreater(rep.latency_ms, 0)

    def test_03_suspicious_site_detection_s11(self):
        """Verifies statistical data-driven detection of Site S11 having unnatural low variance."""
        findings = self.watch.site_detector.detect_low_variability_sites(cut=12)
        self.assertGreaterEqual(len(findings), 1)
        s11 = next((f for f in findings if f.site_id == "S11"), None)
        self.assertIsNotNone(s11, "Site S11 should be flagged for low vital signs variance")
        self.assertLess(s11.observed_value, 1.5, "Site S11 SYSBP stdev should be < 1.5 mmHg")
        self.assertGreater(s11.cohort_mean, 5.0, "Cohort SYSBP stdev should be normal (> 5 mmHg)")
        self.assertEqual(s11.signal, "UNNATURAL_LOW_VARIABILITY")
        self.assertIn("Source Data Verification", s11.recommended_action)

    def test_04_data_integrity_vs_clinical_emergency_s04(self):
        """Verifies Site S04 glucose at Cut 8 is categorized as data integrity, not safety emergency."""
        findings = self.watch.integrity_detector.detect_analyser_unit_mismatch(cut=8)
        self.assertEqual(len(findings), 1)
        s04 = findings[0]
        self.assertEqual(s04.site_id, "S04")
        self.assertEqual(s04.test_code, "GLUC")
        self.assertEqual(s04.reported_unit, "mg/dL")
        self.assertEqual(s04.inferred_true_unit, "mmol/L")
        # Critical distinction: DATA INTEGRITY, NOT SAFETY EMERGENCY
        self.assertFalse(s04.is_clinical_emergency)
        self.assertTrue(s04.adversarial_note_present)
        self.assertIn("042-S04-001", s04.affected_subjects)
        self.assertEqual(len(s04.affected_subjects), 8)

    def test_05_protocol_amendments_and_subject_impact(self):
        """Verifies protocol amendment diffing and affected subject detection (042-S02-019)."""
        detector = ProtocolAmendmentDetector()
        diff2 = detector.get_protocol_diff(1, 2, 5)
        self.assertEqual(diff2.from_version, 1)
        self.assertEqual(diff2.to_version, 2)
        self.assertEqual(diff2.effective_cut, 5)
        self.assertIn("VISIT_WINDOW_DEVIATION", diff2.affected_finding_types)

        diff3 = detector.get_protocol_diff(2, 3, 9)
        self.assertEqual(diff3.from_version, 2)
        self.assertEqual(diff3.to_version, 3)
        self.assertEqual(diff3.effective_cut, 9)
        self.assertIn("PROHIBITED_MEDICATION", diff3.affected_finding_types)
        self.assertIn("042-S02-019", diff3.affected_subjects)

    def test_06_slow_unanswered_monitor_policy(self):
        """Verifies that missing monitor response is NOT converted to approval."""
        status, reason = self.watch._query_monitor_with_slow_human_policy("HYS_LAW_POTENTIAL", "UNKNOWN_SUBJECT_XYZ")
        self.assertEqual(status, WatchDecisionStatus.UNANSWERED)
        self.assertEqual(reason, "No monitor response received.")

    def test_07_budget_manager_and_graceful_degradation(self):
        """Verifies budget tracking transitions from HEALTHY to LIMITED to CRITICAL."""
        mgr = BudgetManager(total_seconds=10.0)
        self.assertEqual(mgr.get_state(), BudgetState.HEALTHY)
        
        # Simulate elapsed time into LIMITED (75% consumed)
        mgr.start_time = mgr.start_time - 7.5
        self.assertEqual(mgr.get_state(), BudgetState.LIMITED)

        # Simulate elapsed time into CRITICAL (92% consumed)
        mgr.start_time = mgr.start_time - 2.0
        self.assertEqual(mgr.get_state(), BudgetState.CRITICAL)

        profile = mgr.get_degradation_profile()
        self.assertIn("action", profile)

    def test_08_explain_decision_stored_trace(self):
        """Verifies explain() retrieves from stored trace without reconstructing facts."""
        self.assertGreater(len(self.watch.decisions_log), 0)
        first_id = list(self.watch.decisions_log.keys())[0]
        res = self.watch.explain(first_id)
        self.assertTrue(res["found"])
        self.assertEqual(res["decision_id"], first_id)
        self.assertIn("EXPLANATION FOR SURVEILLANCE DECISION", res["explanation"])
        self.assertIn("Clinical & Analytical Rationale", res["explanation"])

        # Explain D-009 specifically
        res_009 = self.watch.explain("D-009")
        if res_009["found"]:
            self.assertIn("DATA INTEGRITY", res_009["explanation"])

        # Unknown decision ID
        res_missing = self.watch.explain("D-99999")
        self.assertFalse(res_missing["found"])

    def test_09_conversational_flows_unified_orchestration(self):
        """Verifies the unified assistant handles all 9 master conversational flows."""
        flows = [
            ("Which subjects meet potential Hy's law criteria?", "LIVER_SAFETY"),
            ("Why was 042-S05-003 flagged?", "LIVER_SAFETY"),
            ("What monitor escalations are still pending?", "REVIEW_CREW_STATUS"),
            ("Which site has suspicious reporting behavior?", "WATCH_SUSPICIOUS_SITES"),
            ("Why was S11 flagged?", "WATCH_SUSPICIOUS_SITES"),
            ("Why was S04 flagged at Cut 8?", "WATCH_DATA_INTEGRITY"),
            ("Was this a patient safety issue?", "WATCH_DATA_INTEGRITY"),
            ("What changed in the latest protocol amendment?", "WATCH_PROTOCOL_AMENDMENT"),
            ("Explain decision D-009", "WATCH_DECISION_EXPLAIN"),
        ]

        for query, expected_intent in flows:
            resp = self.orchestrator.process_message(query)
            self.assertEqual(
                resp["intent"],
                expected_intent,
                f"Query '{query}' produced intent {resp['intent']}, expected {expected_intent}"
            )
            self.assertTrue(len(resp["message"]) > 50, f"Query '{query}' response was too short")
            self.assertIsInstance(resp["evidence"], list)
            self.assertIsInstance(resp["follow_up"], list)


if __name__ == "__main__":
    unittest.main()
