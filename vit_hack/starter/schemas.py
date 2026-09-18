"""Schema definitions for Study Sentinel: RecordRef, Question, and Answer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class RecordRef:
    """Universal evidence reference triple (domain, usubjid, seq) or document citation."""
    domain: str
    usubjid: Optional[str] = None
    seq: Optional[int] = None
    document: Optional[str] = None
    section: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {"domain": self.domain}
        if self.usubjid is not None:
            res["usubjid"] = self.usubjid
        if self.seq is not None:
            res["seq"] = self.seq
        if self.document is not None:
            res["document"] = self.document
        if self.section is not None:
            res["section"] = self.section
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> RecordRef:
        return cls(
            domain=data.get("domain", ""),
            usubjid=data.get("usubjid"),
            seq=data.get("seq"),
            document=data.get("document"),
            section=data.get("section"),
        )


@dataclass
class Question:
    """Question schema submitted to Atlas."""
    question_id: str
    text: str
    kind: Optional[str] = None  # count, lookup, finding, trap
    params: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        res: Dict[str, Any] = {
            "question_id": self.question_id,
            "text": self.text,
        }
        if self.kind is not None:
            res["kind"] = self.kind
        if self.params is not None:
            res["params"] = self.params
        return res

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Question:
        return cls(
            question_id=data.get("question_id", ""),
            text=data.get("text", ""),
            kind=data.get("kind"),
            params=data.get("params"),
        )


@dataclass
class Answer:
    """Standardized Answer output schema."""
    question_id: str
    answer: Any
    text: str
    evidence: List[Union[RecordRef, Dict[str, Any]]] = field(default_factory=list)
    confidence: float = 1.0
    steps_used: int = 0
    tokens_used: int = 0

    def to_dict(self) -> Dict[str, Any]:
        formatted_evidence: List[Dict[str, Any]] = []
        for ev in self.evidence:
            if isinstance(ev, RecordRef):
                formatted_evidence.append(ev.to_dict())
            elif isinstance(ev, dict):
                formatted_evidence.append(ev)
            else:
                formatted_evidence.append(dict(ev))

        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "text": self.text,
            "evidence": formatted_evidence,
            "confidence": round(self.confidence, 4),
            "steps_used": self.steps_used,
            "tokens_used": self.tokens_used,
        }
