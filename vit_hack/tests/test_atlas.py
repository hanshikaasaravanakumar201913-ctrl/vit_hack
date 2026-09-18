"""Comprehensive test suite for Stage 1 - ATLAS.

Tests:
- Unit conversion (ukat/L to U/L)
- Reference-range lookup (Central vs Local Site S07)
- Decimal comma handling ('12,4')
- Below-detection handling ('<5' is not 0)
- ND / blank handling
- Malformed / missing fields
- Date parsing (ISO and CDISC DD-MON-YYYY)
- Evidence references and validation
- Hy's law candidate detection & worked example (042-S07-001)
- Cut rebuilding & amendment resilience
- Corrections application (Cut 5 central lab re-issues)
- Trap handling & honest empty answers (Site S01 wrong dose)
- Prohibited medication deviations across protocol versions
- Dosing error detection (Site S09)
"""

import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stage1.atlas import Atlas, StudyGraph
from stage1.dates import days_between, parse_date, within_window
from stage1.evidence import EvidenceValidator
from stage1.normalization import LabNormalizer
from stage1.reasoning import ClinicalReasoning
from stage1.rules import ProtocolRules
from starter.schemas import Answer, Question, RecordRef


class TestAtlasCore(unittest.TestCase):
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

    # 1. Unit conversion & Reference-range lookup
    def test_unit_conversion_and_reference_ranges(self):
        norm = LabNormalizer(self.graph.reference_ranges)

        # Site S07 ALT in ukat/L -> converted to U/L (factor 60)
        rec = norm.normalize("ALT", "3.995", "ukat/L", "S07")
        self.assertTrue(rec.unit_converted)
        self.assertEqual(rec.normalized_unit, "U/L")
        self.assertAlmostEqual(rec.normalized_value, 239.7, places=1)
        self.assertEqual(rec.high, 56.0)
        self.assertTrue(rec.is_above_3x_uln)
        self.assertIn("converted from ukat/L", rec.explanation)

        # Central Lab ALT in U/L
        rec_central = norm.normalize("ALT", "40.0", "U/L", "S01")
        self.assertFalse(rec_central.unit_converted)
        self.assertEqual(rec_central.normalized_value, 40.0)
        self.assertEqual(rec_central.high, 56.0)
        self.assertFalse(rec_central.is_above_uln)

    # 2. Decimal comma
    def test_decimal_comma(self):
        norm = LabNormalizer(self.graph.reference_ranges)
        rec = norm.normalize("ALT", "12,4", "U/L", "S01")
        self.assertEqual(rec.parsed_value, 12.4)
        self.assertEqual(rec.normalized_value, 12.4)

    # 3. Below detection ('<5') is NOT zero
    def test_below_detection(self):
        norm = LabNormalizer(self.graph.reference_ranges)
        parsed = norm.parse_value("<5")
        self.assertTrue(parsed.is_below_detection)
        self.assertEqual(parsed.detection_limit, 5.0)
        self.assertIsNone(parsed.numeric_value)
        self.assertNotEqual(parsed.numeric_value, 0.0, "<5 must NOT be treated as numeric zero")

        rec = norm.normalize("GLUC", "<5", "mg/dL", "S01")
        self.assertIsNone(rec.normalized_value)
        self.assertIn("below detection", rec.explanation)

    # 4. ND / blank
    def test_not_done_and_blank(self):
        norm = LabNormalizer(self.graph.reference_ranges)
        for s in ("ND", "Not Done", "", None):
            parsed = norm.parse_value(s)
            self.assertTrue(parsed.is_not_done)
            self.assertIsNone(parsed.numeric_value)

    # 5. Date parsing
    def test_date_parsing(self):
        d1 = parse_date("2026-03-30")
        d2 = parse_date("28-JAN-2026")
        d3 = parse_date("03-FEB-2026")
        self.assertIsNotNone(d1)
        self.assertIsNotNone(d2)
        self.assertIsNotNone(d3)
        self.assertEqual(d1.year, 2026)
        self.assertEqual(d1.month, 3)
        self.assertEqual(d1.day, 30)
        self.assertEqual(d2.month, 1)
        self.assertEqual(d2.day, 28)

        # Difference and windows
        self.assertEqual(days_between("2026-03-30", "2026-03-30"), 0)
        self.assertEqual(days_between("2026-03-30", "2026-04-13"), 14)
        self.assertTrue(within_window("2026-03-30", "2026-04-13", 14))
        self.assertFalse(within_window("2026-03-30", "2026-04-15", 14))

        # Malformed dates should not crash
        self.assertIsNone(parse_date("not-a-date"))
        self.assertIsNone(parse_date(""))
        self.assertIsNone(parse_date(None))

    # 6. Hy's law worked example (042-S07-001)
    def test_hys_law_worked_example(self):
        q = Question("Q018", "Which subjects meet potential Hy's law criteria?", kind="finding")
        ans = self.atlas.answer(q)
        
        self.assertIn("042-S07-001", ans.answer)
        self.assertIn("042-S05-003", ans.answer)
        self.assertIn("042-S08-014", ans.answer)
        self.assertEqual(len(ans.answer), 3)

        # Check evidence citations: must include LB seq 25 and 27 for 042-S07-001
        ev_triples = [(e["domain"], e["usubjid"], e["seq"]) for e in ans.evidence]
        self.assertIn(("LB", "042-S07-001", 25), ev_triples)
        self.assertIn(("LB", "042-S07-001", 27), ev_triples)

        # Check explanation text
        self.assertIn("239.7 U/L", ans.text)
        self.assertIn("converted from ukat/L", ans.text)

    # 7. Trap handling (Site S01 wrong dose)
    def test_trap_handling(self):
        q = Question("Q031", "Which subjects at site S01 received a wrong dose?", kind="trap")
        ans = self.atlas.answer(q)
        
        # Must return empty list with no invented evidence
        self.assertEqual(ans.answer, [])
        self.assertEqual(ans.evidence, [])
        self.assertGreaterEqual(ans.confidence, 0.8)
        self.assertIn("No dosing errors at site S01", ans.text)

    # 8. Dosing errors at Site S09
    def test_dosing_errors_detection(self):
        q = Question("Q_DOSE", "Which subjects at site S09 received a wrong dose?", kind="finding")
        ans = self.atlas.answer(q)
        
        self.assertGreater(len(ans.answer), 0)
        self.assertIn("042-S09-004", ans.answer)
        for ev in ans.evidence:
            self.assertEqual(ev["domain"], "EX")

    # 9. Discontinuations due to AE
    def test_discontinuations_by_ae(self):
        # Site S07 discontinued by AE should be 0 (trap)
        q_s07 = Question("Q_DS_S07", "How many subjects at site S07 discontinued due to an adverse event?", kind="count")
        ans_s07 = self.atlas.answer(q_s07)
        self.assertEqual(ans_s07.answer, 0)
        self.assertEqual(ans_s07.evidence, [])

        # Site S11 discontinued by AE should be 3
        q_s11 = Question("Q_DS_S11", "How many subjects at site S11 discontinued due to an adverse event?", kind="count")
        ans_s11 = self.atlas.answer(q_s11)
        self.assertEqual(ans_s11.answer, 3)
        self.assertEqual(len(ans_s11.evidence), 3)

    # 10. Prohibited medications across cuts / versions
    def test_prohibited_medications_amendments(self):
        # Build graph at Cut 4 (Protocol v1)
        graph_v1 = StudyGraph(str(self.data_dir))
        graph_v1.build(cut=4)
        atlas_v1 = Atlas(graph_v1)
        ans_v1 = atlas_v1.answer(Question("Q_MED", "Which subjects took prohibited concomitant medications?"))

        # Build graph at Cut 10 (Protocol v3 - adds Sulfonylurea)
        graph_v3 = StudyGraph(str(self.data_dir))
        graph_v3.build(cut=10)
        atlas_v3 = Atlas(graph_v3)
        ans_v3 = atlas_v3.answer(Question("Q_MED", "Which subjects took prohibited concomitant medications?"))

        self.assertGreater(len(ans_v3.answer), len(ans_v1.answer), "Cut 10 should detect additional prohibited medications")

    # 11. Evidence validation & non-existent record filtering
    def test_evidence_validator(self):
        validator = EvidenceValidator(self.graph)
        raw_evidence = [
            {"domain": "LB", "usubjid": "042-S07-001", "seq": 25},  # Valid
            {"domain": "LB", "usubjid": "042-S07-001", "seq": 99999},  # Invalid seq
            {"domain": "FAKE", "usubjid": "042-S07-001", "seq": 1},  # Invalid domain
            {"domain": "LB", "usubjid": "042-S07-001", "seq": 25},  # Duplicate
        ]
        validated = validator.validate_and_deduplicate(raw_evidence)
        self.assertEqual(len(validated), 1)
        self.assertEqual(validated[0], {"domain": "LB", "usubjid": "042-S07-001", "seq": 25})

    # 12. Cut rebuilding & corrections
    def test_cut_rebuilding_and_corrections(self):
        graph = StudyGraph(str(self.data_dir))
        
        # Cut 4
        graph.build(cut=4)
        r4 = graph.get_record("LB", "042-S08-001", 8)
        self.assertEqual(r4["LBORRES"], "26.5")

        # Rebuild at Cut 5 (correction applied)
        graph.build(cut=5)
        r5 = graph.get_record("LB", "042-S08-001", 8)
        self.assertEqual(r5["LBORRES"], "25.92")


if __name__ == "__main__":
    unittest.main()
