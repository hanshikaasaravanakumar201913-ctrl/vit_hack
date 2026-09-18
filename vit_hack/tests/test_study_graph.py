"""Validation script for StudyGraph data loading and representation layer."""

import os
import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stage1.atlas import StudyGraph


class TestStudyGraph(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Locate data directory
        cls.data_dir = PROJECT_ROOT / "DATASET-20260918T152607Z-1-001" / "DATASET" / "hackathon-data" / "hackathon-data"
        if not cls.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {cls.data_dir}")
        cls.graph = StudyGraph(str(cls.data_dir))

    def test_full_build(self):
        """Test building full graph across all cuts."""
        stats = self.graph.build(cut=None)
        print("\nFull build stats:", stats)
        
        self.assertIn("nodes", stats)
        self.assertIn("edges", stats)
        self.assertIn("subjects", stats)
        self.assertEqual(stats["subjects"], 241)
        self.assertGreater(stats["nodes"], 27000)
        self.assertGreater(stats["edges"], 27000)
        self.assertLess(stats["build_time_ms"], 5000, "Build should be very fast (<5s)")

    def test_patient360(self):
        """Test patient360 retrieval for a specific subject."""
        self.graph.build(cut=None)
        p360 = self.graph.patient360("042-S07-001")
        
        self.assertEqual(p360["usubjid"], "042-S07-001")
        self.assertEqual(p360["site_id"], "S07")
        self.assertEqual(p360["arm"], "PLACEBO")
        self.assertIn("LB", p360["records_by_domain"])
        self.assertIn("AE", p360["records_by_domain"])
        self.assertIn("WEEK8", p360["visits"])
        
        # Check specific known record: LB seq 25 (ALT at WEEK8)
        rec = self.graph.get_record("LB", "042-S07-001", 25)
        self.assertIsNotNone(rec)
        self.assertEqual(rec["LBTESTCD"], "ALT")
        self.assertEqual(rec["VISIT"], "WEEK8")
        self.assertEqual(rec["LBORRESU"], "ukat/L")

    def test_cut_filtering(self):
        """Test that data cut filtering limits records properly."""
        stats_cut1 = self.graph.build(cut=1)
        stats_cut5 = self.graph.build(cut=5)
        stats_full = self.graph.build(cut=None)
        
        print(f"\nCut 1 nodes: {stats_cut1['nodes']}, Cut 5 nodes: {stats_cut5['nodes']}, Full nodes: {stats_full['nodes']}")
        self.assertLess(stats_cut1["nodes"], stats_cut5["nodes"])
        self.assertLess(stats_cut5["nodes"], stats_full["nodes"])

    def test_corrections_application(self):
        """Test that corrections are applied at and after their specified cut."""
        # Record LB|042-S08-001|8 was old_value 26.5, new_value 25.92 at cut 5
        self.graph.build(cut=4)
        rec_cut4 = self.graph.get_record("LB", "042-S08-001", 8)
        self.assertIsNotNone(rec_cut4)
        self.assertEqual(rec_cut4["LBORRES"], "26.5")

        self.graph.build(cut=5)
        rec_cut5 = self.graph.get_record("LB", "042-S08-001", 8)
        self.assertIsNotNone(rec_cut5)
        self.assertEqual(rec_cut5["LBORRES"], "25.92")

    def test_malformed_rows_resilience(self):
        """Test that safe parsing handles edge cases without crashing."""
        self.assertIsNone(self.graph._safe_int(None))
        self.assertIsNone(self.graph._safe_int(""))
        self.assertIsNone(self.graph._safe_int("invalid"))
        self.assertEqual(self.graph._safe_int("42"), 42)
        self.assertEqual(self.graph._safe_int(42.0), 42)


if __name__ == "__main__":
    unittest.main()
