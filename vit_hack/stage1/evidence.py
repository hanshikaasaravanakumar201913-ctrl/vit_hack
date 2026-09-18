"""Evidence validation and citation verifier for Study Sentinel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Set, Tuple, Union

if TYPE_CHECKING:
    from stage1.atlas import StudyGraph

from starter.schemas import RecordRef


class EvidenceValidator:
    """Validates that cited records exist in the study and deduplicates references."""

    def __init__(self, graph: Any):
        self.graph = graph

    def validate_and_deduplicate(
        self,
        evidence_list: List[Union[RecordRef, Dict[str, Any]]],
        expected_domain: Union[str, Set[str], None] = None,
        expected_usubjids: Union[Set[str], List[str], None] = None,
    ) -> List[Dict[str, Any]]:
        """Verifies that every RecordRef exists in the study graph and deduplicates.
        
        Args:
            evidence_list: List of RecordRef objects or dictionaries.
            expected_domain: Optional domain or set of domains to filter by.
            expected_usubjids: Optional set of subject IDs to filter by.
            
        Returns:
            Deduplicated list of validated evidence dictionaries.
        """
        validated: List[Dict[str, Any]] = []
        seen_keys: Set[Tuple[Any, ...]] = set()

        if isinstance(expected_domain, str):
            expected_domain = {expected_domain.upper()}
        elif expected_domain:
            expected_domain = {d.upper() for d in expected_domain}

        subj_filter = set(expected_usubjids) if expected_usubjids else None

        for item in evidence_list:
            if isinstance(item, RecordRef):
                item_dict = item.to_dict()
            elif isinstance(item, dict):
                item_dict = dict(item)
            else:
                continue

            domain = item_dict.get("domain", "").strip().upper()
            if not domain:
                continue

            # Document reference (e.g. protocol, lab-manual)
            if domain == "DOC":
                doc = item_dict.get("document", "")
                sec = item_dict.get("section", "")
                doc_key = ("DOC", doc, sec)
                if doc_key not in seen_keys:
                    seen_keys.add(doc_key)
                    validated.append(item_dict)
                continue

            usubjid = item_dict.get("usubjid", "").strip()
            raw_seq = item_dict.get("seq")
            if not usubjid or raw_seq is None:
                continue

            try:
                seq = int(raw_seq)
            except (ValueError, TypeError):
                continue

            # Domain check if restricted
            if expected_domain and domain not in expected_domain:
                continue

            # Subject check if restricted
            if subj_filter is not None and usubjid not in subj_filter:
                continue

            # Check existence in graph
            ref_key = (domain, usubjid, seq)
            if ref_key not in self.graph.records_by_ref:
                # Discard nonexistent records
                continue

            dedup_key = (domain, usubjid, seq)
            if dedup_key in seen_keys:
                continue

            seen_keys.add(dedup_key)
            validated.append({"domain": domain, "usubjid": usubjid, "seq": seq})

        return validated
