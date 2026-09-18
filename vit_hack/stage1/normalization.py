"""Laboratory normalization and reference range evaluation for Study Sentinel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ParsedLabResult:
    """Represents parsed laboratory measurement result."""
    raw_value: str
    numeric_value: Optional[float]
    is_valid: bool
    is_below_detection: bool = False
    detection_limit: Optional[float] = None
    is_not_done: bool = False


@dataclass
class NormalizedLabRecord:
    """Fully normalized laboratory record with reference ranges and evaluation."""
    testcd: str
    raw_value: str
    raw_unit: str
    parsed_value: Optional[float]
    normalized_value: Optional[float]
    normalized_unit: str
    unit_converted: bool
    conversion_factor: float
    low: Optional[float]
    high: Optional[float]  # ULN (Upper Limit of Normal)
    lab_source: str
    ratio_to_uln: Optional[float]
    is_above_uln: bool
    is_above_2x_uln: bool
    is_above_3x_uln: bool
    explanation: str


class LabNormalizer:
    """Laboratory normalization engine handling units, non-numeric values, and ranges."""

    def __init__(self, reference_ranges: Optional[List[Dict[str, Any]]] = None):
        self.ranges: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self.ranges_by_test_lab: Dict[Tuple[str, str], Dict[str, Any]] = {}

        if reference_ranges:
            self.load_ranges(reference_ranges)

    def load_ranges(self, reference_ranges: List[Dict[str, Any]]) -> None:
        """Indexes reference range rows by (test, unit, lab) and (test, lab)."""
        self.ranges.clear()
        self.ranges_by_test_lab.clear()

        for row in reference_ranges:
            test = row.get("LBTESTCD", "").strip().upper()
            unit = row.get("UNIT", "").strip()
            lab = row.get("LAB", "").strip().upper()

            low_val = None
            high_val = None
            try:
                if row.get("LOW"):
                    low_val = float(str(row["LOW"]).replace(",", "."))
                if row.get("HIGH"):
                    high_val = float(str(row["HIGH"]).replace(",", "."))
            except (ValueError, TypeError):
                pass

            data = {
                "test": test,
                "unit": unit,
                "lab": lab,
                "low": low_val,
                "high": high_val,
            }
            self.ranges[(test, unit.upper(), lab)] = data
            self.ranges_by_test_lab[(test, lab)] = data

    def parse_value(self, val_str: Any) -> ParsedLabResult:
        """Parses LBORRES string according to clinical protocol specifications.
        
        Handles:
        - Regular numeric values ('40.4', '12.4')
        - Decimal commas ('12,4' -> 12.4)
        - '<5', '<0.5' (below detection limit; NOT treated as 0.0)
        - 'ND', blank, empty (not done / missing)
        """
        if val_str is None:
            return ParsedLabResult(raw_value="", numeric_value=None, is_valid=False, is_not_done=True)

        s = str(val_str).strip()
        if not s:
            return ParsedLabResult(raw_value=s, numeric_value=None, is_valid=False, is_not_done=True)

        s_upper = s.upper()
        if s_upper in ("ND", "NOT DONE", "BLANK", "NULL", "NONE", "."):
            return ParsedLabResult(raw_value=s, numeric_value=None, is_valid=False, is_not_done=True)

        # Handle '<' below detection limit (e.g. '<5', '< 0.5')
        if s.startswith("<"):
            limit_str = s[1:].strip().replace(",", ".")
            try:
                limit_val = float(limit_str)
                return ParsedLabResult(
                    raw_value=s,
                    numeric_value=None,  # NOT 0.0
                    is_valid=True,
                    is_below_detection=True,
                    detection_limit=limit_val,
                )
            except ValueError:
                return ParsedLabResult(raw_value=s, numeric_value=None, is_valid=False)

        # Standard numeric or decimal comma
        clean_str = s.replace(",", ".")
        try:
            val = float(clean_str)
            return ParsedLabResult(raw_value=s, numeric_value=val, is_valid=True)
        except ValueError:
            return ParsedLabResult(raw_value=s, numeric_value=None, is_valid=False)

    def get_reference_range(self, testcd: str, unit: str, site_id: str) -> Dict[str, Any]:
        """Resolves the appropriate reference range for a test, unit, and site."""
        test_upper = testcd.strip().upper()
        unit_upper = unit.strip().upper()
        site_upper = site_id.strip().upper()

        # 1. Exact match (test, unit, site)
        if (test_upper, unit_upper, site_upper) in self.ranges:
            return self.ranges[(test_upper, unit_upper, site_upper)]

        # 2. Site match (test, site)
        if (test_upper, site_upper) in self.ranges_by_test_lab:
            return self.ranges_by_test_lab[(test_upper, site_upper)]

        # 3. Central lab with matching unit
        if (test_upper, unit_upper, "CENTRAL") in self.ranges:
            return self.ranges[(test_upper, unit_upper, "CENTRAL")]

        # 4. Fallback to Central lab by test
        if (test_upper, "CENTRAL") in self.ranges_by_test_lab:
            return self.ranges_by_test_lab[(test_upper, "CENTRAL")]

        # Hardcoded fallback defaults from reference_ranges.csv if table wasn't loaded
        defaults = {
            "ALT": {"low": 7.0, "high": 56.0, "unit": "U/L", "lab": "CENTRAL"},
            "AST": {"low": 10.0, "high": 40.0, "unit": "U/L", "lab": "CENTRAL"},
            "BILI": {"low": 0.1, "high": 1.2, "unit": "mg/dL", "lab": "CENTRAL"},
            "HBA1C": {"low": 4.0, "high": 5.6, "unit": "%", "lab": "CENTRAL"},
            "GLUC": {"low": 70.0, "high": 99.0, "unit": "mg/dL", "lab": "CENTRAL"},
            "CREAT": {"low": 0.6, "high": 1.2, "unit": "mg/dL", "lab": "CENTRAL"},
        }
        if site_upper == "S07":
            if test_upper == "ALT":
                return {"low": 0.12, "high": 0.93, "unit": "ukat/L", "lab": "S07"}
            if test_upper == "AST":
                return {"low": 0.17, "high": 0.67, "unit": "ukat/L", "lab": "S07"}

        return defaults.get(test_upper, {"low": None, "high": None, "unit": unit, "lab": "CENTRAL"})

    def normalize(self, testcd: str, raw_value: Any, raw_unit: str, site_id: str) -> NormalizedLabRecord:
        """Normalizes lab value and evaluates against ULN."""
        test_upper = str(testcd).strip().upper()
        unit_str = str(raw_unit).strip()
        site_str = str(site_id).strip().upper()

        parsed = self.parse_value(raw_value)
        ref_range = self.get_reference_range(test_upper, unit_str, site_str)

        norm_val = parsed.numeric_value
        norm_unit = unit_str
        unit_converted = False
        factor = 1.0

        # Handle ukat/L conversion to U/L: 1 ukat/L = 60 U/L
        # Site S07 reports ALT/AST in ukat/L
        if unit_str in ("ukat/L", "µkat/L", "UKAT/L") and test_upper in ("ALT", "AST"):
            if norm_val is not None:
                norm_val = round(norm_val * 60.0, 4)
            norm_unit = "U/L"
            unit_converted = True
            factor = 60.0
            # Compare against conventional Central ULN (ALT: 56, AST: 40)
            uln = 56.0 if test_upper == "ALT" else 40.0
            low = 7.0 if test_upper == "ALT" else 10.0
            lab_source = f"{site_str}->CENTRAL"
        else:
            uln = ref_range.get("high")
            low = ref_range.get("low")
            lab_source = ref_range.get("lab", "CENTRAL")

        ratio_to_uln = None
        is_above_uln = False
        is_above_2x = False
        is_above_3x = False

        if norm_val is not None and uln is not None and uln > 0:
            ratio_to_uln = round(norm_val / uln, 4)
            is_above_uln = norm_val > uln
            is_above_2x = norm_val > 2.0 * uln
            is_above_3x = norm_val > 3.0 * uln

        # Build explanation string
        if parsed.is_below_detection:
            explanation = f"{test_upper} <{parsed.detection_limit} {unit_str} (below detection)"
        elif parsed.is_not_done:
            explanation = f"{test_upper} not done"
        elif norm_val is not None and uln is not None:
            mult = round(ratio_to_uln, 1) if ratio_to_uln else 0.0
            if unit_converted:
                explanation = f"{test_upper} {norm_val} {norm_unit} ({mult}xULN, converted from {unit_str})"
            else:
                explanation = f"{test_upper} {norm_val} {norm_unit} ({mult}xULN)"
        else:
            explanation = f"{test_upper} {parsed.raw_value} {unit_str}"

        return NormalizedLabRecord(
            testcd=test_upper,
            raw_value=parsed.raw_value,
            raw_unit=unit_str,
            parsed_value=parsed.numeric_value,
            normalized_value=norm_val,
            normalized_unit=norm_unit,
            unit_converted=unit_converted,
            conversion_factor=factor,
            low=low,
            high=uln,
            lab_source=lab_source,
            ratio_to_uln=ratio_to_uln,
            is_above_uln=is_above_uln,
            is_above_2x_uln=is_above_2x,
            is_above_3x_uln=is_above_3x,
            explanation=explanation,
        )
