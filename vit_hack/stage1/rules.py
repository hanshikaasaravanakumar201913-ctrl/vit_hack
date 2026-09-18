"""Protocol and Rule Engine for Study Sentinel.

Loads and applies the protocol version in force for a given data cut or explicit version.
Handles visit windows, prohibited medications, dosing rules, inclusion/exclusion,
and safety evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class ProtocolRules:
    """Version-aware clinical trial rules derived from protocol specifications."""
    protocol_version: int = 1
    cut: Optional[int] = None

    # Visit schedule & window
    visit_window_days: int = 7

    # Prohibited medications
    prohibited_med_classes: Set[str] = field(default_factory=set)
    prohibited_med_terms: Set[str] = field(default_factory=set)

    # Dosing standards (mg)
    drug_arm_dose: float = 10.0
    placebo_arm_dose: float = 0.0

    # Liver safety (Hy's law)
    hys_law_alt_ast_factor: float = 3.0
    hys_law_bili_factor: float = 2.0
    hys_law_window_days: int = 14

    # Inclusion / Exclusion thresholds
    min_age: int = 18
    max_age: int = 75
    min_scr_hba1c: float = 7.0
    max_scr_hba1c: float = 10.5
    scr_hepatic_exclusion_factor: float = 2.0  # ALT or AST > 2 x ULN
    scr_renal_exclusion_creatinine: Optional[float] = None  # Added in Amendment 2

    @classmethod
    def for_cut(cls, cut: Optional[int] = None) -> ProtocolRules:
        """Determines protocol version in force at a given cut and instantiates rules."""
        # Mapping from cuts.csv:
        # Cuts 1-4: version 1
        # Cuts 5-8: version 2
        # Cuts 9-12: version 3
        if cut is None or cut >= 9:
            version = 3 if cut is None or cut >= 9 else 1
        elif cut >= 5:
            version = 2
        else:
            version = 1

        return cls.for_version(version=version, cut=cut)

    @classmethod
    def for_version(cls, version: int = 1, cut: Optional[int] = None) -> ProtocolRules:
        """Instantiates protocol rules for an explicit protocol version (1, 2, or 3)."""
        rules = cls(protocol_version=version, cut=cut)

        if version == 1:
            rules.visit_window_days = 7
            rules.prohibited_med_classes = {"SYSTEMIC_GLUCOCORTICOID"}
            rules.prohibited_med_terms = {"PREDNISOLONE"}
            rules.scr_renal_exclusion_creatinine = None
        elif version == 2:
            # Amendment 2: Tightens visit window to +-3 days, adds renal exclusion (>1.5 mg/dL)
            rules.visit_window_days = 3
            rules.prohibited_med_classes = {"SYSTEMIC_GLUCOCORTICOID"}
            rules.prohibited_med_terms = {"PREDNISOLONE"}
            rules.scr_renal_exclusion_creatinine = 1.5
        elif version >= 3:
            # Amendment 3: Adds Sulfonylurea to prohibited medications
            rules.visit_window_days = 3
            rules.prohibited_med_classes = {"SYSTEMIC_GLUCOCORTICOID", "SULFONYLUREA"}
            rules.prohibited_med_terms = {"PREDNISOLONE", "GLIBENCLAMIDE"}
            rules.scr_renal_exclusion_creatinine = 1.5

        return rules
