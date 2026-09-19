"""
Tests for ATLAS Conversational Intent System, Protocol QA, and Multi-Turn Follow-Ups.

Validates:
1. Casual greetings, identity, capabilities, gratitude, and help without StudyGraph queries.
2. Protocol inquiries (inclusion/exclusion criteria, visit windows, prohibited medications, dosing schedules).
3. Conversational follow-ups (pre-AE history, screening vs latest lab comparison, compliance evaluation, medication relevance).
4. Ambiguous query clarification when patient context is missing.
5. Out-of-scope redirection to STUDY-042 domain with helpful follow-ups.
6. Clean explanatory answer formatting without database dumps.
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stage1.atlas import Atlas, StudyGraph
from stage1.ai.context import ConversationContext, ConversationStore
from stage1.ai.orchestrator import AtlasConversationalOrchestrator


class TestConversationalIntents(unittest.TestCase):
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
    # 1. Casual Conversation (Zero Database Dumps)
    # -------------------------------------------------------------------------
    def test_casual_greeting_hello(self):
        res = self.orchestrator.chat("Hello", conversation_id="conv-greet-1")
        self.assertIn(res["intent"], ("GREETING", "CASUAL_CONVERSATION"))
        self.assertEqual(res["intent_category"], "GREETING")
        self.assertIn("ATLAS", res["message"])
        self.assertNotIn("No records met", res["message"])
        self.assertEqual(len(res["evidence"]), 0)
        self.assertTrue(len(res["followup_suggestions"]) >= 3)

    def test_casual_greeting_hi(self):
        res = self.orchestrator.chat("Hi there!", conversation_id="conv-greet-2")
        self.assertIn(res["intent"], ("GREETING", "CASUAL_CONVERSATION"))
        self.assertEqual(res["intent_category"], "GREETING")
        self.assertIn("ATLAS", res["message"])
        self.assertNotIn("No records met", res["message"])

    def test_identity_and_capabilities(self):
        res = self.orchestrator.chat("Who are you and what can you do?", conversation_id="conv-identity")
        self.assertEqual(res["intent"], "CASUAL_CONVERSATION")
        self.assertIn("Clinical Study Intelligence", res["message"])
        self.assertIn("Hy's Law", res["message"])
        self.assertIn("Protocol Compliance", res["message"])
        self.assertNotIn("No records met", res["message"])

    def test_gratitude(self):
        res = self.orchestrator.chat("Thank you so much!", conversation_id="conv-thanks")
        self.assertEqual(res["intent"], "CASUAL_CONVERSATION")
        self.assertIn("welcome", res["message"].lower())
        self.assertNotIn("No records met", res["message"])

    def test_help_request(self):
        res = self.orchestrator.chat("Help", conversation_id="conv-help")
        self.assertEqual(res["intent"], "CASUAL_CONVERSATION")
        self.assertIn("STUDY-042", res["message"])
        self.assertTrue(len(res["followup_suggestions"]) >= 3)

    def test_polite_status_query(self):
        res = self.orchestrator.chat("How are you?", conversation_id="conv-status")
        self.assertEqual(res["intent"], "CASUAL_CONVERSATION")
        self.assertIn("monitoring", res["message"].lower())
        self.assertNotIn("No records met", res["message"])

    # -------------------------------------------------------------------------
    # 2. Protocol Knowledge QA (Direct from ProtocolRules)
    # -------------------------------------------------------------------------
    def test_protocol_inclusion_exclusion(self):
        res = self.orchestrator.chat("What are the inclusion criteria?", conversation_id="conv-proto-1")
        self.assertEqual(res["intent"], "PROTOCOL_INQUIRY")
        self.assertIn("18 to 75", res["message"])
        self.assertIn("HbA1c", res["message"])
        self.assertIn("Exclusion Criteria", res["message"])

    def test_protocol_visit_windows(self):
        res = self.orchestrator.chat("What is the visit window?", conversation_id="conv-proto-2")
        self.assertEqual(res["intent"], "PROTOCOL_INQUIRY")
        self.assertIn("±7 days", res["message"])
        self.assertIn("±3 days", res["message"])

    def test_protocol_prohibited_medications(self):
        res = self.orchestrator.chat("Is Glibenclamide permitted under the protocol?", conversation_id="conv-proto-3")
        self.assertEqual(res["intent"], "PROTOCOL_INQUIRY")
        self.assertIn("prohibited", res["message"].lower())
        self.assertIn("Glibenclamide", res["message"])
        self.assertIn("Amendment 3", res["message"])

    def test_protocol_dosing_schedule(self):
        res = self.orchestrator.chat("What is the study drug dose for the active arm?", conversation_id="conv-proto-4")
        self.assertEqual(res["intent"], "PROTOCOL_INQUIRY")
        self.assertIn("10 mg", res["message"])
        self.assertIn("0 mg", res["message"])

    def test_protocol_hys_law_definition(self):
        res = self.orchestrator.chat("What is the protocol definition of Hy's law?", conversation_id="conv-proto-5")
        self.assertEqual(res["intent"], "PROTOCOL_INQUIRY")
        self.assertIn("3× ULN", res["message"])
        self.assertIn("2× ULN", res["message"])
        self.assertIn("14-day", res["message"])

    # -------------------------------------------------------------------------
    # 3. Conversational Follow-Ups & Context Continuity
    # -------------------------------------------------------------------------
    def test_conversational_followup_pre_ae(self):
        conv_id = "conv-followup-1"
        # Turn 1: Focus on subject 042-S07-001
        res1 = self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)
        self.assertEqual(res1["active_subject"], "042-S07-001")

        # Turn 2: Follow-up asking what happened before the adverse event
        res2 = self.orchestrator.chat("What happened before the adverse event?", conversation_id=conv_id)
        self.assertEqual(res2["intent"], "FOLLOWUP_PRE_AE")
        self.assertIn("042-S07-001", res2["message"])
        self.assertIn("Pre-Adverse Event Timeline", res2["message"])
        self.assertTrue(len(res2["evidence"]) > 0)

    def test_conversational_followup_lab_comparison(self):
        conv_id = "conv-followup-2"
        # Turn 1: Focus on subject 042-S07-001
        self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)

        # Turn 2: Compare screening labs with latest labs
        res2 = self.orchestrator.chat("Compare their screening labs with their latest labs", conversation_id=conv_id)
        self.assertEqual(res2["intent"], "FOLLOWUP_LAB_COMPARISON")
        self.assertIn("042-S07-001", res2["message"])
        self.assertIn("Screening", res2["message"])
        self.assertIn("ALT", res2["message"])
        self.assertTrue(len(res2["evidence"]) > 0)

    def test_conversational_followup_compliance(self):
        conv_id = "conv-followup-3"
        # Turn 1: Focus on subject 042-S09-004 (who received 20mg deviation)
        self.orchestrator.chat("Tell me about subject 042-S09-004", conversation_id=conv_id)

        # Turn 2: Check protocol compliance
        res2 = self.orchestrator.chat("Was the patient compliant with the protocol?", conversation_id=conv_id)
        self.assertEqual(res2["intent"], "FOLLOWUP_COMPLIANCE")
        self.assertIn("042-S09-004", res2["message"])
        self.assertIn("Dosing Compliance", res2["message"])
        self.assertTrue(len(res2["evidence"]) > 0)

    def test_conversational_followup_medication_relevance(self):
        conv_id = "conv-followup-4"
        # Turn 1: Focus on subject 042-S07-001 (who took Glibenclamide)
        self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)

        # Turn 2: Are medications relevant
        res2 = self.orchestrator.chat("Are any of those medications relevant to the current finding?", conversation_id=conv_id)
        self.assertEqual(res2["intent"], "FOLLOWUP_MEDICATION_RELEVANCE")
        self.assertIn("042-S07-001", res2["message"])
        self.assertIn("Glibenclamide", res2["message"])
        self.assertIn("PROHIBITED", res2["message"])

    def test_conversational_followup_supporting_evidence(self):
        conv_id = "conv-followup-5"
        # Turn 1: Query liver safety
        self.orchestrator.chat("What are the liver safety findings for subject 042-S07-001?", conversation_id=conv_id)

        # Turn 2: What evidence supports that?
        res2 = self.orchestrator.chat("What evidence supports that?", conversation_id=conv_id)
        self.assertEqual(res2["intent"], "EVIDENCE_REQUEST")
        self.assertTrue(len(res2["evidence"]) > 0)
        self.assertIn("verified clinical record", res2["message"])

    # -------------------------------------------------------------------------
    # 4. Ambiguous Questions (Missing Patient Context)
    # -------------------------------------------------------------------------
    def test_ambiguous_question_missing_subject(self):
        res = self.orchestrator.chat("What was the ALT?", conversation_id="conv-ambig-1")
        self.assertEqual(res["intent"], "CLARIFICATION_NEEDED")
        self.assertIn("Could you please specify", res["message"])
        self.assertTrue(any("042-S07-001" in s for s in res["followup_suggestions"]))

    # -------------------------------------------------------------------------
    # 5. Out of Scope Handling
    # -------------------------------------------------------------------------
    def test_out_of_scope_cooking(self):
        res = self.orchestrator.chat("What is the best recipe for pasta?", conversation_id="conv-oos-1")
        self.assertEqual(res["intent"], "OUT_OF_SCOPE")
        self.assertIn("ATLAS specializes strictly in STUDY-042", res["message"])
        self.assertTrue(len(res["followup_suggestions"]) >= 3)

    # -------------------------------------------------------------------------
    # 6. Comprehensive 14 Conversational Flows (Section 19 Benchmark)
    # -------------------------------------------------------------------------
    def test_conv_1_greeting_hi(self):
        res = self.orchestrator.chat("hi", conversation_id="conv-bench-1")
        self.assertEqual(res["intent_category"], "GREETING")
        self.assertIn("ATLAS", res["message"])
        self.assertNotIn("No records met", res["message"])
        self.assertEqual(len(res["evidence"]), 0)

    def test_conv_2_candy_dietary(self):
        res = self.orchestrator.chat("can I eat a candy?", conversation_id="conv-bench-2")
        self.assertEqual(res["intent_category"], "CASUAL_CONVERSATION")
        self.assertNotIn("No records met", res["message"])
        self.assertIn("STUDY-042", res["message"])
        self.assertIn("glycemic", res["message"].lower())

    def test_conv_3_general_knowledge_placebo(self):
        res = self.orchestrator.chat("what is a placebo?", conversation_id="conv-bench-3")
        self.assertEqual(res["intent_category"], "GENERAL_KNOWLEDGE")
        self.assertNotIn("No records met", res["message"])
        self.assertIn("Placebo in Clinical Trials", res["message"])
        self.assertIn("STUDY-042", res["message"])
        self.assertIn("0 mg", res["message"])

    def test_conv_4_mortality_query(self):
        res = self.orchestrator.chat("how many people died?", conversation_id="conv-bench-4")
        self.assertEqual(res["intent_category"], "SAFETY_QUERY")
        self.assertNotIn("No records met", res["message"])
        self.assertIn("zero reported deaths", res["message"].lower())
        self.assertIn("241", res["message"])

    def test_conv_5_hospitalization_clarification(self):
        res = self.orchestrator.chat("how many are currently admitted?", conversation_id="conv-bench-5")
        self.assertEqual(res["intent_category"], "AMBIGUOUS")
        self.assertNotIn("No records met", res["message"])
        self.assertIn("hospitalized", res["message"].lower())
        self.assertIn("AESHOSP", res["message"])

    def test_conv_6_to_9_subject_followup_chain(self):
        conv_id = "conv-bench-chain"
        # Turn 1: Tell me about subject 042-S07-001
        res1 = self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)
        self.assertEqual(res1["intent_category"], "PATIENT_QUERY")
        self.assertIn("042-S07-001", res1["message"])
        self.assertIn("Site S07", res1["message"])

        # Turn 2: What medications were they taking?
        res2 = self.orchestrator.chat("What medications were they taking?", conversation_id=conv_id)
        self.assertEqual(res2["intent_category"], "FOLLOW_UP")
        self.assertIn("042-S07-001", res2["message"])
        self.assertIn("Glibenclamide", res2["message"])

        # Turn 3: What about their liver?
        res3 = self.orchestrator.chat("What about their liver?", conversation_id=conv_id)
        self.assertEqual(res3["intent_category"], "SAFETY_QUERY")
        self.assertIn("042-S07-001", res3["message"])
        self.assertIn("ALT", res3["message"])

        # Turn 4: Was that serious?
        res4 = self.orchestrator.chat("Was that serious?", conversation_id=conv_id)
        self.assertEqual(res4["intent_category"], "FOLLOW_UP")
        self.assertIn("042-S07-001", res4["message"])
        self.assertIn("serious", res4["message"].lower())

    def test_conv_10_cohort_dosing_deviations(self):
        res = self.orchestrator.chat("Which subjects at site S09 received a wrong dose?", conversation_id="conv-bench-10")
        self.assertEqual(res["intent_category"], "COHORT_QUERY")
        self.assertNotIn("No records met", res["message"])
        self.assertIn("S09", res["message"])

    def test_conv_11_protocol_amendment(self):
        res = self.orchestrator.chat("What changed in the latest protocol amendment?", conversation_id="conv-bench-11")
        self.assertEqual(res["intent_category"], "PROTOCOL_QUERY")
        self.assertIn("Amendment", res["message"])

    def test_conv_12_cohort_hys_law(self):
        res = self.orchestrator.chat("Which subjects meet potential Hy's law criteria?", conversation_id="conv-bench-12")
        self.assertEqual(res["intent_category"], "SAFETY_QUERY")
        self.assertIn("042-S07-001", res["message"])
        self.assertIn("042-S05-003", res["message"])

    def test_conv_13_fact_check(self):
        conv_id = "conv-bench-13"
        self.orchestrator.chat("Tell me about subject 042-S07-001", conversation_id=conv_id)
        res = self.orchestrator.chat("Fact check this finding", conversation_id=conv_id)
        self.assertEqual(res["intent_category"], "FACT_CHECK")
        self.assertIn("042-S07-001", res["message"])

    def test_conv_14_out_of_scope_pizza(self):
        res = self.orchestrator.chat("Who invented pizza?", conversation_id="conv-bench-14")
        self.assertEqual(res["intent_category"], "OUT_OF_SCOPE")
        self.assertIn("pizza", res["message"].lower())
        self.assertIn("ATLAS specializes strictly in STUDY-042", res["message"])

    def test_conv_15_ambiguous_without_subject(self):
        res = self.orchestrator.chat("Tell me about that subject", conversation_id="conv-bench-15")
        self.assertEqual(res["intent_category"], "AMBIGUOUS")
        self.assertIn("specify", res["message"].lower())


if __name__ == "__main__":
    unittest.main()
