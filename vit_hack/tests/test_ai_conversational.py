"""
Tests for ATLAS AI-Powered Conversational Clinical Study Assistant.
Covers multi-turn context memory, pronoun resolution, out-of-scope redirection,
StudyGraph fact-checking, AI medical reviews, and deterministic clinical engine integration.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stage1.atlas import Atlas, StudyGraph
from stage1.ai.context import ConversationContext, ConversationStore
from stage1.ai.provider import DeterministicClinicalProvider, get_ai_provider
from stage1.ai.orchestrator import AtlasConversationalOrchestrator
from stage2.escalations import execute_fact_check
from stage2.models import Escalation, GateDecision, SiteQuery, QueryStatus


class TestAIConversationalEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data_dir = (
            PROJECT_ROOT
            / "DATASET-20260918T152607Z-1-001"
            / "DATASET"
            / "hackathon-data"
            / "hackathon-data"
        )
        cls.graph = StudyGraph(str(cls.data_dir))
        cls.graph.build(cut=None)
        cls.atlas = Atlas(cls.graph)
        cls.orchestrator = AtlasConversationalOrchestrator(atlas=cls.atlas)


    def setUp(self):
        self.store = ConversationStore()
        self.orchestrator.store = self.store

    # -------------------------------------------------------------------------
    # 1. Multi-turn pronoun resolution and context memory
    # -------------------------------------------------------------------------
    def test_pronoun_resolution_they_their(self):
        ctx = ConversationContext(conversation_id="test-conv-1")
        ctx.active_subject = "042-S07-001"
        
        resolved = ctx.resolve_pronouns("What about their liver results?")
        self.assertIn("042-S07-001", resolved)

        resolved_they = ctx.resolve_pronouns("Did they take any prohibited medications?")
        self.assertIn("042-S07-001", resolved_they)

        resolved_pt = ctx.resolve_pronouns("What doses did that patient receive?")
        self.assertIn("042-S07-001", resolved_pt)

    def test_multi_turn_conversation_flow(self):
        conv_id = "test-multi-turn"
        # Turn 1: Ask about subject 042-S07-001
        res1 = self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)
        self.assertEqual(res1["active_subject"], "042-S07-001")
        self.assertIn("042-S07-001", res1["message"])
        self.assertTrue(len(res1["evidence"]) > 0)
        self.assertTrue(len(res1["followup_suggestions"]) > 0)

        # Turn 2: Follow-up using pronoun "their"
        res2 = self.orchestrator.chat("What about their liver results?", conversation_id=conv_id)
        self.assertEqual(res2["active_subject"], "042-S07-001")
        self.assertIn("ALT", res2["message"])
        self.assertTrue("μkat/L" in res2["message"] or "ukat/L" in res2["message"] or "µkat/L" in res2["message"])

        # Turn 3: Follow-up asking about Hy's law criteria
        res3 = self.orchestrator.chat("Does this meet Hy's law criteria?", conversation_id=conv_id)
        self.assertTrue("hy's law" in res3["message"].lower() or "hy's" in res3["message"].lower())
        self.assertTrue(any(ev["domain"] == "LB" for ev in res3["evidence"]))

    def test_conversation_context_isolation(self):
        # Two different sessions should have isolated subject contexts
        self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id="session-A")
        self.orchestrator.chat("Tell me about subject 042-S05-003", conversation_id="session-B")

        ctx_a = self.orchestrator.context_store.get("session-A")
        ctx_b = self.orchestrator.context_store.get("session-B")
        self.assertEqual(ctx_a.active_subject, "042-S07-001")
        self.assertEqual(ctx_b.active_subject, "042-S05-003")

    # -------------------------------------------------------------------------
    # 2. Out-of-Scope and Refusal Handling
    # -------------------------------------------------------------------------
    def test_out_of_scope_query_refusal(self):
        res = self.orchestrator.chat("What is the capital of France?", conversation_id="test-oos")
        self.assertIn("ATLAS specializes strictly in STUDY-042", res["message"])
        self.assertEqual(len(res["evidence"]), 0)
        self.assertTrue(len(res["followup_suggestions"]) > 0)

        res2 = self.orchestrator.chat("Write me a poem about clinical trials", conversation_id="test-oos-2")
        self.assertIn("ATLAS specializes strictly in STUDY-042", res2["message"])

    def test_ambiguous_query_clarification(self):
        res = self.orchestrator.chat("Tell me about the patient with elevated labs", conversation_id="test-clarify")
        self.assertIn("Could you please specify", res["message"])
        self.assertTrue(any("042-S07-001" in s for s in res["followup_suggestions"]))

    # -------------------------------------------------------------------------
    # 3. Clinical Intent Coverage and Evidence Traceability
    # -------------------------------------------------------------------------
    def test_hys_law_cohort_inquiry(self):
        res = self.orchestrator.chat("Which subjects meet potential Hy's law criteria?", conversation_id="test-hys")
        self.assertIn("042-S07-001", res["message"])
        self.assertIn("042-S05-003", res["message"])
        self.assertTrue(len(res["evidence"]) > 0)
        for ev in res["evidence"]:
            self.assertEqual(ev["domain"], "LB")
            self.assertIn("usubjid", ev)
            self.assertIn("seq", ev)

    def test_wrong_dose_inquiry(self):
        res = self.orchestrator.chat("Which subjects at site S09 received a wrong dose?", conversation_id="test-dose")
        self.assertIn("042-S09-004", res["message"])
        self.assertIn("20", res["message"])
        self.assertTrue(any(ev["domain"] == "EX" for ev in res["evidence"]))

    def test_prohibited_concomitant_medications(self):
        res = self.orchestrator.chat("Which subjects took prohibited concomitant medications?", conversation_id="test-cm")
        self.assertIn("042-S02-019", res["message"])
        self.assertTrue(any(ev["domain"] == "CM" for ev in res["evidence"]))

    def test_discontinuation_adverse_events(self):
        res = self.orchestrator.chat("How many subjects at site S11 discontinued due to an adverse event?", conversation_id="test-ds")
        self.assertIn("042-S11-008", res["message"])
        self.assertTrue(any(ev["domain"] == "DS" or ev["domain"] == "AE" for ev in res["evidence"]))

    def test_site_s07_unit_conversion(self):
        res = self.orchestrator.chat("What are the liver transaminase results for subject 042-S07-001?", conversation_id="test-s07")
        self.assertTrue("μkat/L" in res["message"] or "ukat/L" in res["message"] or "µkat/L" in res["message"])
        self.assertIn("Site S07", res["message"])

    # -------------------------------------------------------------------------
    # 4. ReviewCrew StudyGraph Fact-Checking Loop
    # -------------------------------------------------------------------------
    def test_realtime_studygraph_fact_check(self):
        esc = Escalation(
            id="ESC-TEST-001",
            finding_code="HYS_LAW_POTENTIAL",
            target_id="042-S07-001",
            title="Potential Hy's Law Escalation",
            summary="Subject 042-S07-001 met Hy's Law biochemical criteria at Week 8.",
            rationale="Peak ALT elevation with hyperbilirubinemia.",
            citations=[("LB", "042-S07-001", 42)],
        )

        # Query 1: Screening baseline ALT
        fc1 = execute_fact_check(self.graph, esc, "What was the screening baseline ALT for this subject?")
        self.assertIn("within the normal reference range", fc1["interpretation"])
        self.assertTrue(any("Screening ALT" in f for f in fc1["findings"]))

        # Query 2: Concomitant medications
        fc2 = execute_fact_check(self.graph, esc, "Did the subject take concomitant medications?")
        self.assertIn("concomitant medication", fc2["interpretation"].lower())

        # Query 3: Hospitalization check
        fc3 = execute_fact_check(self.graph, esc, "Was this subject hospitalized?")
        self.assertIn("hospitalization", fc3["interpretation"].lower())

    # -------------------------------------------------------------------------
    # 5. Escalation Decision Transitions and Doctor Comments
    # -------------------------------------------------------------------------
    def test_escalation_monitoring_and_comment(self):
        esc = Escalation(
            id="ESC-TEST-002",
            finding_code="UNCODED_SAE_HOSPITALIZATION",
            target_id="042-S05-006",
            title="Hospitalization AE escalation",
            summary="Subject hospitalized for chest pain.",
            rationale="Uncoded SAE requiring safety triage.",
            citations=[("AE", "042-S05-006", 1)],
        )

        self.assertEqual(esc.status, "PENDING")
        esc.status = GateDecision.MONITORING.value
        esc.monitor_comments.append({
            "author": "Dr. Smith",
            "comment": "Patient discharged without sequelae. Keep on active observation.",
            "suggested_action": "HOLD_IN_MONITORING",
        })

        d = esc.to_dict()
        self.assertEqual(d["status"], "MONITORING")
        self.assertEqual(len(d["monitor_comments"]), 1)
        self.assertEqual(d["monitor_comments"][0]["author"], "Dr. Smith")

    # -------------------------------------------------------------------------
    # 6. Provider Abstraction
    # -------------------------------------------------------------------------
    def test_deterministic_clinical_provider(self):
        provider = get_ai_provider()
        self.assertIsInstance(provider, DeterministicClinicalProvider)
        resp = provider.generate("Tell me about subject 042-S07-001")
        self.assertIn("042-S07-001", resp)


if __name__ == "__main__":
    unittest.main()
