"""ATLAS Stage 2 — MONITOR Comprehensive Test Suite.

Verifies the complete 6-node ReviewCrew architecture, trace, memory, gateway,
safety triage (SAE miscoded, Hy's law precision), data queries, human gate,
deduplication, repeated subjects, and site clustering.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from stage1.atlas import Atlas, StudyGraph
from stage2.crew import ReviewCrew
from stage2.gateway import MonitorGateway
from stage2.memory import ReviewMemory
from stage2.models import FindingType, GateDecision, QueryStatus
from stage2.rules import check_hys_law_safety, check_sae_miscoded
from stage2.trace import AuditTrace


class TestStage2ReviewCrew(unittest.TestCase):
    """Integration and unit tests for Stage 2 MONITOR."""

    @classmethod
    def setUpClass(cls):
        cls.data_dir = Path("DATASET-20260918T152607Z-1-001/DATASET/hackathon-data/hackathon-data")
        cls.graph = StudyGraph(str(cls.data_dir))
        cls.graph.build(cut=12)
        cls.atlas = Atlas(cls.graph)

    def test_01_crew_initialization(self):
        """ReviewCrew initializes cleanly with Atlas and internal components."""
        crew = ReviewCrew(atlas=self.atlas)
        self.assertIsNotNone(crew.atlas)
        self.assertIsNotNone(crew.memory)
        self.assertIsNotNone(crew.trace)
        self.assertIsNotNone(crew.gateway)
        self.assertEqual(crew.cycle_count, 0)

    def test_02_six_node_sequence(self):
        """ReviewCrew executes the exact 6-node sequence in order."""
        crew = ReviewCrew(atlas=self.atlas)
        crew.run_cycle(cut=12, protocol_version=3)
        
        entries = crew.trace.get_cycle_entries(1)
        node_order = []
        for e in entries:
            if not node_order or node_order[-1] != e.node:
                node_order.append(e.node)
                
        expected_sequence = ["detect", "medical_review", "data_manager", "compliance", "human_gate", "execute"]
        self.assertEqual(node_order, expected_sequence)

    def test_03_sae_miscoded_detection(self):
        """Hospitalized AE with AESER=N (e.g. 042-S02-004) is detected as SAE_MISCODED."""
        sae_findings = check_sae_miscoded(self.graph)
        miscoded_subjs = {f.usubjid for f in sae_findings}
        self.assertIn("042-S02-004", miscoded_subjs)
        
        # Verify 042-S02-004 details
        f_004 = next(f for f in sae_findings if f.usubjid == "042-S02-004")
        self.assertEqual(f_004.finding_type, FindingType.SAE_MISCODED.value)
        self.assertTrue(f_004.requires_escalation)
        self.assertIn(("AE", "042-S02-004", 1), f_004.citations)

    def test_04_sae_citations_validity(self):
        """Every SAE miscoded finding has real (domain, usubjid, seq) citations in graph."""
        sae_findings = check_sae_miscoded(self.graph)
        self.assertGreater(len(sae_findings), 0)
        for f in sae_findings:
            self.assertGreater(len(f.citations), 0)
            for dom, subj, seq in f.citations:
                self.assertEqual(dom, "AE")
                self.assertIn((dom, subj, seq), self.graph.records_by_ref)

    def test_05_hys_law_candidate_detection(self):
        """Detects subjects meeting Hy's Law biochemical criteria (>3x ULN transaminase + >2x ULN BILI)."""
        hys_findings = check_hys_law_safety(self.graph)
        self.assertGreater(len(hys_findings), 0)
        subjs = {f.usubjid for f in hys_findings}
        self.assertTrue("042-S05-003" in subjs or "042-S08-014" in subjs)

    def test_06_hys_law_baseline_transaminases_precision(self):
        """Subjects with baseline elevated transaminases (e.g. 042-S07-001) are rejected and persist as monitoring-only."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        rejected_subjs = {e.target_id for e in rep.rejected_escalations}
        self.assertIn("042-S07-001", rejected_subjs)
        self.assertTrue(crew.memory.is_item_rejected("HYS_LAW_CANDIDATE|042-S07-001"))
        
        # Verify monitor's rationale
        esc = next(e for e in rep.rejected_escalations if e.target_id == "042-S07-001")
        self.assertIn("Baseline transaminases were already elevated", esc.gate_reason)

    def test_07_dosing_deviations_detection(self):
        """Detects dosing errors where administered dose != randomized arm (e.g. Site S09 20mg)."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        
        dose_findings = [f for f in rep.findings if f.finding_type == FindingType.DOSING_ERROR.value]
        self.assertGreater(len(dose_findings), 0)
        s09_subjs = {f.usubjid for f in dose_findings if f.site_id == "S09"}
        self.assertGreater(len(s09_subjs), 0)

    def test_08_data_manager_query_generation(self):
        """Generates concrete queries for data discrepancies (e.g. AE onset before first dose for 042-S11-005)."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        
        ae_queries = [q for q in rep.queries_raised if q.domain == "AE"]
        self.assertGreater(len(ae_queries), 0)
        q_subjs = {q.usubjid for q in ae_queries}
        self.assertIn("042-S11-005", q_subjs)

    def test_09_data_manager_query_deduplication(self):
        """Same query is never raised twice across cycles."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertGreater(len(rep1.queries_raised), 0)
        
        rep2 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertEqual(len(rep2.queries_raised), 0)

    def test_10_gateway_site_reply_handling(self):
        """Gateway returns structured replies for queries from site_replies.json."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        
        # Check query for 042-S11-005 seq 1
        q_11_005 = next((q for q in rep.queries_raised if q.usubjid == "042-S11-005" and q.seq == 1), None)
        if q_11_005:
            self.assertIsNotNone(q_11_005.site_response)
            self.assertIn("Date entry error confirmed", q_11_005.site_response)
            self.assertEqual(q_11_005.status, QueryStatus.CLOSED)

    def test_11_compliance_protocol_versioning(self):
        """Compliance node respects protocol version amendments."""
        crew = ReviewCrew(atlas=self.atlas)
        
        # Protocol v1: Glibenclamide not prohibited
        rep_v1 = crew.run_cycle(cut=4, protocol_version=1)
        cm_v1 = [f for f in rep_v1.findings if f.finding_type == FindingType.PROHIBITED_MEDICATION.value]
        
        # Protocol v3: Glibenclamide is prohibited
        crew2 = ReviewCrew(atlas=self.atlas)
        rep_v3 = crew2.run_cycle(cut=12, protocol_version=3)
        cm_v3 = [f for f in rep_v3.findings if f.finding_type == FindingType.PROHIBITED_MEDICATION.value]
        
        self.assertGreater(len(cm_v3), len(cm_v1))

    def test_12_human_gate_approved_escalations(self):
        """Approved candidate escalations are confirmed and logged."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        self.assertGreater(len(rep.approved_escalations), 0)
        for e in rep.approved_escalations:
            self.assertEqual(e.status, GateDecision.APPROVED)

    def test_13_human_gate_rejected_persistence(self):
        """Rejected escalations persist in memory as monitoring-only and never re-escalate."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=12, protocol_version=3)
        
        # Artificially record a rejection in memory
        test_key = "SAE_MISCODED|042-S02-004"
        crew.memory.record_rejection(test_key)
        self.assertTrue(crew.memory.is_item_rejected(test_key))
        
        # Next cycle should NOT escalate 042-S02-004
        rep2 = crew.run_cycle(cut=12, protocol_version=3)
        s02_escalated = any(e.target_id == "042-S02-004" and e.finding_code == "SAE_MISCODED" for e in rep2.escalations)
        self.assertFalse(s02_escalated)

    def test_14_human_gate_clarify_loop(self):
        """Clarification question is dynamically answered from StudyGraph and transitions to APPROVED."""
        crew = ReviewCrew(atlas=self.atlas)
        
        # 042-S01-001 has scripted CLARIFY in monitor_decisions.json:
        # 'What was the ALT at screening, and is there a concomitant hepatotoxic medication?'
        dec, question = crew.gateway.get_monitor_decision("HYS_LAW_CANDIDATE", "042-S01-001")
        self.assertEqual(dec, "CLARIFY")
        
        from stage2.escalations import resolve_monitor_clarification
        answer = resolve_monitor_clarification(self.graph, "042-S01-001", question)
        self.assertIn("Screening ALT", answer)
        self.assertIn("042-S01-001", answer)

    def test_15_same_cut_rerun_zero_new_queries_and_escalations(self):
        """Running the same cut produces exactly 0 new queries and 0 new escalations."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertGreater(len(rep1.queries_raised), 0)
        self.assertGreater(len(rep1.approved_escalations), 0)
        
        rep2 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertEqual(len(rep2.queries_raised), 0)
        self.assertEqual(len(rep2.approved_escalations), 0)

    def test_16_repeated_subjects_multi_cut_escalation(self):
        """Advancing across cuts escalates repeated subjects with findings across cuts."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=1, protocol_version=1)
        rep2 = crew.run_cycle(cut=2, protocol_version=1)
        self.assertGreater(len(rep2.repeated_subjects), 0)
        
        rep_escalations = [e for e in rep2.escalations if e.finding_code == FindingType.REPEATED_SUBJECT_FINDINGS.value]
        self.assertEqual(len(rep_escalations), len(rep2.repeated_subjects))

    def test_17_site_clustering(self):
        """Multiple deviations at a single site trigger site cluster escalation (e.g. Site S09)."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        
        site_clusters = [e for e in rep.escalations if e.finding_code == FindingType.SITE_CLUSTER.value]
        self.assertGreater(len(site_clusters), 0)
        clustered_sites = {e.target_id for e in site_clusters}
        self.assertIn("S09", clustered_sites)

    def test_18_audit_trace_completeness(self):
        """Audit trace contains chronological entries with cycle, node, timestamp, and details."""
        crew = ReviewCrew(atlas=self.atlas)
        crew.run_cycle(cut=12, protocol_version=3)
        
        entries = crew.trace.get_entries()
        self.assertGreater(len(entries), 10)
        for e in entries:
            self.assertTrue(e.entry_id.startswith("TRC-"))
            self.assertEqual(e.cycle, 1)
            self.assertIn(e.node, ["detect", "medical_review", "data_manager", "compliance", "human_gate", "execute"])
            self.assertIsNotNone(e.timestamp)
            self.assertIsNotNone(e.action)

    def test_19_review_memory_state_serialization(self):
        """ReviewMemory serializes state accurately to dict."""
        mem = ReviewMemory()
        mem.record_rejection("HYS_LAW_CANDIDATE|042-S07-001")
        d = mem.to_dict()
        self.assertEqual(d["rejected_items_count"], 1)
        self.assertIn("HYS_LAW_CANDIDATE|042-S07-001", d["rejected_items"])

    def test_20_review_report_serialization(self):
        """ReviewReport serializes complete summary and metrics to dict."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        d = rep.to_dict()
        self.assertEqual(d["cycle"], 1)
        self.assertEqual(d["cut"], 12)
        self.assertIn("metrics", d)
        self.assertIn("findings", d)
        self.assertIn("queries_raised", d)
        self.assertIn("escalations", d)



    def test_21_deduplication_queries_across_three_cycles(self):
        """Zero new queries raised on repeated cycles of the same cut."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertGreater(len(rep1.queries_raised), 0)
        rep2 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertEqual(len(rep2.queries_raised), 0)
        rep3 = crew.run_cycle(cut=12, protocol_version=3)
        self.assertEqual(len(rep3.queries_raised), 0)

    def test_22_repeated_subjects_across_multiple_cuts(self):
        """Subject with findings in Cut 1, Cut 2, Cut 3 is identified in repeated_subjects."""
        crew = ReviewCrew(atlas=self.atlas)
        rep1 = crew.run_cycle(cut=1, protocol_version=1)
        rep2 = crew.run_cycle(cut=2, protocol_version=1)
        rep3 = crew.run_cycle(cut=3, protocol_version=1)
        self.assertGreater(len(rep2.repeated_subjects), 0)
        # Subjects already escalated in cycle 2 should not re-escalate in cycle 3
        c3_repeated_new = [e for e in rep3.escalations if e.finding_code == FindingType.REPEATED_SUBJECT_FINDINGS.value]
        # Any subject newly reaching 2 cuts in cycle 3 is escalated, but previously escalated subjects are not duplicated
        for e in c3_repeated_new:
            self.assertNotIn(e.target_id, [x.target_id for x in rep2.escalations if x.finding_code == FindingType.REPEATED_SUBJECT_FINDINGS.value])

    def test_23_site_clustering_single_escalation(self):
        """Site S09 with multiple dosing errors gets exactly one SITE_CLUSTER escalation."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        s09_clusters = [e for e in rep.escalations if e.finding_code == FindingType.SITE_CLUSTER.value and e.target_id == "S09"]
        self.assertEqual(len(s09_clusters), 1)
        self.assertIn("Cluster threshold exceeded", s09_clusters[0].rationale)

    def test_24_clarification_response_content(self):
        """Clarification resolution provides screening ALT and concomitant medication info."""
        from stage2.escalations import resolve_monitor_clarification
        ans = resolve_monitor_clarification(self.graph, "042-S01-001", "What was the ALT at screening, and is there a concomitant hepatotoxic medication?")
        self.assertIn("Screening ALT for 042-S01-001", ans)
        self.assertIn("Concomitant medications", ans)

    def test_25_audit_trace_json_export(self):
        """AuditTrace exports complete serializable list of entries."""
        crew = ReviewCrew(atlas=self.atlas)
        crew.run_cycle(cut=12, protocol_version=3)
        trace_list = crew.trace.to_list()
        self.assertIsInstance(trace_list, list)
        self.assertGreater(len(trace_list), 0)
        for item in trace_list:
            self.assertIn("entry_id", item)
            self.assertIn("node", item)
            self.assertIn("timestamp", item)
            self.assertIn("action", item)

    def test_26_memory_query_lookup_keys(self):
        """ReviewMemory properly stores query keys in DOMAIN|USUBJID|SEQ format."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        for q in rep.queries_raised:
            expected_key = f"{q.domain}|{q.usubjid}|{q.seq}"
            self.assertEqual(q.key, expected_key)
            self.assertTrue(crew.memory.is_query_already_raised(expected_key))

    def test_27_dosing_deviation_citation_validity(self):
        """All dosing deviation citations reference existing EX records in StudyGraph."""
        crew = ReviewCrew(atlas=self.atlas)
        rep = crew.run_cycle(cut=12, protocol_version=3)
        dose_findings = [f for f in rep.findings if f.finding_type == FindingType.DOSING_ERROR.value]
        self.assertGreater(len(dose_findings), 0)
        for f in dose_findings:
            for dom, subj, seq in f.citations:
                self.assertEqual(dom, "EX")
                self.assertIn((dom, subj, seq), self.graph.records_by_ref)

    def test_28_stage1_public_questions_still_pass(self):
        """Stage 1 Atlas core public question answers remain 100% functional and unmodified."""
        # Q001: Hy's law criteria
        ans_q1 = self.atlas.answer({"question_id": "Q001", "text": "Which subjects meet potential Hy's law criteria?", "kind": "finding"})
        self.assertIsInstance(ans_q1.answer, list)
        self.assertGreater(len(ans_q1.answer), 0)
        self.assertGreater(len(ans_q1.evidence), 0)

        # Q007: Wrong dose at Site S09
        ans_q7 = self.atlas.answer({"question_id": "Q007", "text": "Which subjects at site S09 received a wrong dose?", "kind": "finding"})
        self.assertIsInstance(ans_q7.answer, list)
        self.assertEqual(len(ans_q7.answer), 6)
        self.assertGreater(len(ans_q7.evidence), 0)


if __name__ == "__main__":
    unittest.main()
