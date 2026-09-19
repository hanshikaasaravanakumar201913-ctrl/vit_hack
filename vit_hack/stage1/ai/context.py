"""ATLAS Conversational Session Context and Reference Resolution.

Maintains multi-turn conversation memory, resolves relative pronouns
("they", "their", "that patient", "those results"), tracks active clinical
entities, and manages conversation stores.
"""

from __future__ import annotations

import datetime
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ConversationContext:
    """Multi-turn conversation session state for clinical inquiries."""
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())
    
    # Message history: list of {role, content, timestamp, intent, evidence, entities}
    messages: List[Dict[str, Any]] = field(default_factory=list)
    
    # Active clinical focus
    active_subject: Optional[str] = None
    active_domain: Optional[str] = None
    active_records: List[Dict[str, Any]] = field(default_factory=list)
    referenced_subjects: List[str] = field(default_factory=list)
    
    # Clinical investigation context
    last_finding_type: Optional[str] = None
    last_intent: Optional[str] = None
    last_protocol_version: int = 3
    last_cut: Optional[int] = 12
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(
        self,
        role: str,
        content: str,
        intent: Optional[str] = None,
        evidence: Optional[List[Dict[str, Any]]] = None,
        entities: Optional[Dict[str, Any]] = None,
        follow_up: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Appends a turn to conversation history and updates session timestamp."""
        msg = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "intent": intent,
            "evidence": evidence or [],
            "entities": entities or {},
            "follow_up": follow_up or [],
        }
        self.messages.append(msg)
        self.updated_at = msg["timestamp"]

        # Keep rolling message window (last 30 messages)
        if len(self.messages) > 30:
            self.messages = self.messages[-30:]

        return msg

    def set_active_subject(self, usubjid: str) -> None:
        """Sets the active subject and updates the list of referenced subjects."""
        clean_subj = usubjid.strip().upper()
        self.active_subject = clean_subj
        if clean_subj not in self.referenced_subjects:
            self.referenced_subjects.append(clean_subj)

    def resolve_references(self, query_text: str) -> Tuple[str, Dict[str, Any]]:
        """Resolves conversational pronouns and references to explicit clinical entities.
        
        Examples:
        - "What about their liver results?" -> resolves "their" to active_subject.
        - "Why was this patient flagged?" -> resolves "this patient" to active_subject.
        - "Show me the records" -> resolves to active_records from previous turn.
        - "Was that serious?" -> resolves to last adverse event or finding.
        """
        resolved_entities: Dict[str, Any] = {}
        text = query_text.strip()
        text_lower = text.lower()

        # 1. Direct USUBJID in query? (e.g. 042-S07-001)
        subj_match = re.search(r"\b(\d{3}-S\d{2}-\d{3})\b", text, re.IGNORECASE)
        if subj_match:
            subj_id = subj_match.group(1).upper()
            self.set_active_subject(subj_id)
            resolved_entities["subject"] = subj_id
            resolved_entities["explicit_subject"] = True
        elif self.active_subject:
            # Check for pronouns: "their", "they", "this patient", "that patient", "this subject", "that subject", "the patient"
            pronoun_pattern = r"\b(their|they|them|he|she|him|her|this patient|that patient|the patient|this subject|that subject|the subject)\b"
            if re.search(pronoun_pattern, text_lower) or any(k in text_lower for k in ["what happened to", "what about", "why was", "why were"]):
                resolved_entities["subject"] = self.active_subject
                resolved_entities["resolved_via_context"] = True

        # 2. Domain / Finding References
        if any(w in text_lower for w in ["liver", "alt", "ast", "bilirubin", "hy's law", "hys law"]):
            resolved_entities["domain"] = "LB"
            resolved_entities["finding_category"] = "LIVER_SAFETY"
        elif any(w in text_lower for w in ["medication", "concomitant", "drug", "taking", "prohibited"]):
            resolved_entities["domain"] = "CM"
            resolved_entities["finding_category"] = "MEDICATIONS"
        elif any(w in text_lower for w in ["dose", "dosing", "exposure", "treatment", "placebo", "10mg", "20mg"]):
            resolved_entities["domain"] = "EX"
            resolved_entities["finding_category"] = "DOSING"
        elif any(w in text_lower for w in ["adverse event", "ae", "sae", "hospitalized", "serious"]):
            resolved_entities["domain"] = "AE"
            resolved_entities["finding_category"] = "ADVERSE_EVENTS"
        elif any(w in text_lower for w in ["vital", "blood pressure", "pulse", "hr", "temp"]):
            resolved_entities["domain"] = "VS"
            resolved_entities["finding_category"] = "VITALS"

        # 3. Evidence / Record request
        if any(phrase in text_lower for phrase in ["show me the records", "show the records", "show the evidence", "show me the evidence", "actual records", "supporting records"]):
            resolved_entities["request_evidence_cards"] = True
            if self.active_records:
                resolved_entities["records"] = self.active_records

        return text, resolved_entities

    def resolve_pronouns(self, query_text: str) -> str:
        """Helper to resolve pronouns in query_text and return augmented text with subject."""
        text, entities = self.resolve_references(query_text)
        if entities.get("resolved_via_context") and entities.get("subject"):
            return f"{text} (Referring to subject {entities['subject']})"
        return text

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active_subject": self.active_subject,
            "active_domain": self.active_domain,
            "referenced_subjects": self.referenced_subjects,
            "last_finding_type": self.last_finding_type,
            "last_intent": self.last_intent,
            "message_count": len(self.messages),
            "messages": self.messages,
        }


class ConversationStore:
    """Thread-safe in-memory session manager for conversation contexts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: Dict[str, ConversationContext] = {}

    def get_or_create(self, conversation_id: Optional[str] = None) -> ConversationContext:
        """Retrieves an existing conversation context or initializes a new one."""
        with self._lock:
            if conversation_id and conversation_id in self._store:
                return self._store[conversation_id]

            cid = conversation_id or str(uuid.uuid4())
            ctx = ConversationContext(conversation_id=cid)
            self._store[cid] = ctx
            return ctx

    def get(self, conversation_id: str) -> Optional[ConversationContext]:
        """Gets a conversation context by ID."""
        with self._lock:
            return self._store.get(conversation_id)

    def delete(self, conversation_id: str) -> bool:
        """Removes a conversation context."""
        with self._lock:
            return self._store.pop(conversation_id, None) is not None

    def list_conversations(self) -> List[Dict[str, Any]]:
        """Lists active conversation summaries."""
        with self._lock:
            return [ctx.to_dict() for ctx in self._store.values()]
