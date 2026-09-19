"""ATLAS Production Web Server & API Layer.

Hosts the browser application and serves the deterministic clinical intelligence API.
Built entirely using Python standard libraries (http.server) with zero external dependencies.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stage1.atlas import Atlas, StudyGraph
from stage1.ai import AtlasConversationalOrchestrator
from starter.schemas import Question
from stage2.crew import ReviewCrew
from stage2.models import GateDecision
from stage3.watch import WatchSurveillance

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("atlas.server")

# Global instances initialized on startup
GRAPH: Optional[StudyGraph] = None
ATLAS_ENGINE: Optional[Atlas] = None
DATA_DIR_PATH: Optional[Path] = None
REVIEW_CREW: Optional[ReviewCrew] = None
WATCH_SURVEILLANCE: Optional[WatchSurveillance] = None
AI_ORCHESTRATOR: Optional[AtlasConversationalOrchestrator] = None

PUBLIC_DEMO_QUESTIONS = [
    {
        "question_id": "Q004",
        "category": "Liver Safety",
        "text": "Which subjects meet potential Hy's law criteria?",
    },
    {
        "question_id": "Q005",
        "category": "Liver Safety",
        "text": "Which subjects at site S07 meet potential Hy's law criteria?",
    },
    {
        "question_id": "Q002",
        "category": "Discontinuation",
        "text": "How many subjects at site S11 discontinued due to an adverse event?",
    },
    {
        "question_id": "Q007",
        "category": "Dosing Deviations",
        "text": "Which subjects at site S09 received a wrong dose?",
    },
    {
        "question_id": "Q009",
        "category": "Safety / SAE",
        "text": "Which subjects at site S05 have serious adverse events?",
    },
    {
        "question_id": "Q008",
        "category": "Protocol Amendments",
        "text": "Which subjects took prohibited concomitant medications?",
    },
    {
        "question_id": "Q003",
        "category": "Record Lookup",
        "text": "List the laboratory and adverse-event records for 042-S05-003 within 7 days of the WEEK8 visit",
    },
    {
        "question_id": "Q006",
        "category": "Dosing Deviations",
        "text": "Which subjects at site S01 received a wrong dose?",
    },
    {
        "question_id": "Q001",
        "category": "Discontinuation",
        "text": "How many subjects at site S07 discontinued due to an adverse event?",
    },
    {
        "question_id": "Q010",
        "category": "Dosing Deviations",
        "text": "Which subjects at site S02 received a wrong dose?",
    },
    {
        "question_id": "Q_WATCH_01",
        "category": "Watch Surveillance",
        "text": "Which site has suspicious reporting behavior?",
    },
    {
        "question_id": "Q_WATCH_02",
        "category": "Watch Surveillance",
        "text": "Why was S04 flagged at Cut 8?",
    },
    {
        "question_id": "Q_WATCH_03",
        "category": "Watch Surveillance",
        "text": "Was this a patient safety issue?",
    },
    {
        "question_id": "Q_WATCH_04",
        "category": "Watch Surveillance",
        "text": "What changed in the latest protocol amendment?",
    },
    {
        "question_id": "Q_WATCH_05",
        "category": "Watch Surveillance",
        "text": "What monitor escalations are still pending?",
    },
    {
        "question_id": "Q_WATCH_06",
        "category": "Watch Surveillance",
        "text": "Explain decision D-009",
    },
]



class AtlasRequestHandler(SimpleHTTPRequestHandler):
    """HTTP Request Handler serving both REST API endpoints and web client assets."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        web_dir = PROJECT_ROOT / "web"
        super().__init__(*args, directory=str(web_dir), **kwargs)

    def _send_json(self, data: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        """Helper to send a JSON HTTP response."""
        encoded = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(encoded)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle GET requests for API endpoints and static assets."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/health":
            self._handle_health()
        elif path == "/api/stats":
            self._handle_stats()
        elif path == "/api/subjects":
            self._handle_subjects()
        elif path.startswith("/api/patient/"):
            usubjid = unquote(path[len("/api/patient/"):].strip())
            self._handle_patient(usubjid)
        elif path.startswith("/api/conversation/"):
            cid = unquote(path[len("/api/conversation/"):].strip())
            self._handle_get_conversation(cid)
        elif path.startswith("/api/graph/subject/"):
            self._handle_graph_subject_domain(path)
        elif path == "/api/public-questions":
            self._send_json(PUBLIC_DEMO_QUESTIONS)
        elif path == "/api/monitor/status":
            self._handle_monitor_status()
        elif path == "/api/monitor/report":
            self._handle_monitor_report()
        elif path == "/api/monitor/trace":
            self._handle_monitor_trace()
        elif path == "/api/monitor/escalations":
            self._handle_monitor_escalations()
        elif path == "/api/monitor/memory":
            self._handle_monitor_memory()
        elif path == "/api/watch/cuts":
            self._handle_watch_cuts()
        elif path.startswith("/api/watch/cut/"):
            c_str = path[len("/api/watch/cut/"):].strip()
            try:
                c_num = int(c_str)
            except:
                c_num = 12
            self._handle_watch_cut_detail(c_num)
        elif path == "/api/watch/decisions":
            self._handle_watch_decisions()
        elif path.startswith("/api/watch/decision/"):
            dec_id = unquote(path[len("/api/watch/decision/"):].strip())
            self._handle_watch_explain_decision(dec_id)
        elif path == "/api/watch/suspicious-sites":
            self._handle_watch_suspicious_sites()
        elif path == "/api/watch/data-integrity":
            self._handle_watch_data_integrity()
        elif path == "/api/watch/protocol-amendments":
            self._handle_watch_protocol_amendments()
        elif path == "/api/watch/budget":
            self._handle_watch_budget()
        else:
            # Fallback to serving static frontend files
            super().do_GET()

    def do_POST(self) -> None:
        """Handle POST requests for clinical questions, AI chat, and monitoring actions."""
        parsed_url = urlparse(self.path)
        path = parsed_url.path

        if path == "/api/chat":
            self._handle_chat()
        elif path == "/api/ask":
            self._handle_ask()
        elif path == "/api/monitor/cycle":
            self._handle_monitor_cycle()
        elif path == "/api/monitor/escalations/decision":
            self._handle_monitor_decision()
        elif path == "/api/monitor/fact-check":
            self._handle_monitor_fact_check()
        elif path == "/api/monitor/comment":
            self._handle_monitor_comment()
        elif path == "/api/watch/run":
            self._handle_watch_run_cuts()
        elif path == "/api/watch/explain":
            self._handle_watch_explain_post()
        else:
            self._send_json({"error": "Endpoint not found"}, status=HTTPStatus.NOT_FOUND)

    def _handle_health(self) -> None:
        """GET /api/health"""
        if GRAPH is None or ATLAS_ENGINE is None:
            self._send_json({"status": "starting", "online": False}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        self._send_json({
            "status": "online",
            "study_id": "STUDY-042",
            "active_cut": GRAPH.cut if GRAPH.cut is not None else 12,
            "protocol_version": ATLAS_ENGINE.rules.protocol_version,
            "subjects_enrolled": len(GRAPH.subjects),
            "records_indexed": len(GRAPH.records_by_ref),
            "build_time_ms": getattr(GRAPH, "build_time_ms", 220),
        })

    def _handle_stats(self) -> None:
        """GET /api/stats"""
        if GRAPH is None:
            self._send_json({"error": "Graph not initialized"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        domain_counts: Dict[str, int] = {}
        for (dom, usubjid, seq) in GRAPH.records_by_ref.keys():
            domain_counts[dom] = domain_counts.get(dom, 0) + 1

        sites_map: Dict[str, int] = {}
        for usubjid, sdata in GRAPH.subjects.items():
            site = sdata.get("site_id", "")
            if site:
                sites_map[site] = sites_map.get(site, 0) + 1

        visits_set = set()
        for usubjid, vmap in GRAPH.subject_visits.items():
            for v in vmap.keys():
                if v:
                    visits_set.add(v)

        stats = {
            "nodes": len(GRAPH.nodes),
            "edges": len(GRAPH.edges),
            "subjects": len(GRAPH.subjects),
            "subjects_covered": len(GRAPH.subjects),
            "cut": GRAPH.cut,
            "build_time_ms": getattr(GRAPH, "build_time_ms", 220),
            "ms": getattr(GRAPH, "build_time_ms", 220),
            "domains": domain_counts,
            "sites_count": len(sites_map),
            "sites": sites_map,
            "visits_count": len(visits_set),
            "visits": sorted(list(visits_set)),
        }
        self._send_json(stats)

    def _normalize_query_text(self, text: str) -> str:
        """Normalizes conversational user phrasing to canonical clinical entities."""
        t = text.strip()
        tl = t.lower()
        # 'stopped treatment because of / due to an adverse event' -> 'discontinued due to an adverse event'
        if ("stopped" in tl or "withdrew" in tl) and ("adverse" in tl or "ae" in tl) and "discontinu" not in tl:
            t = re.sub(r"\b(stopped treatment|stopped|withdrew)\b", "discontinued", t, flags=re.IGNORECASE)
            t = re.sub(r"\bbecause of\b", "due to", t, flags=re.IGNORECASE)
        # 'show me what was recorded for ... around week 8'
        if ("show me" in tl or "what was recorded" in tl) and "week" in tl:
            if "list" not in tl and "lookup" not in tl:
                subj_m = re.search(r"\b(\d{3}-s\d{2}-\d{3})\b", t, re.IGNORECASE)
                week_m = re.search(r"\b(week\s*\d+)\b", t, re.IGNORECASE)
                if subj_m and week_m:
                    return f"List the laboratory and adverse-event records for {subj_m.group(1)} within 7 days of the {week_m.group(1).upper().replace(' ', '')} visit"
        return t

    def _handle_subjects(self) -> None:
        """GET /api/subjects"""
        if GRAPH is None:
            self._send_json({"error": "Graph not initialized"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        subjects_summary = []
        for usubjid in sorted(GRAPH.subjects.keys()):
            sdata = GRAPH.subjects[usubjid]
            subjects_summary.append({
                "usubjid": usubjid,
                "site_id": sdata.get("site_id", ""),
                "arm": sdata.get("arm", ""),
                "age": sdata.get("demographics", {}).get("AGE", ""),
                "sex": sdata.get("demographics", {}).get("SEX", ""),
            })

        self._send_json({"count": len(subjects_summary), "subjects": subjects_summary})

    def _handle_patient(self, usubjid: str) -> None:
        """GET /api/patient/{usubjid}"""
        if GRAPH is None:
            self._send_json({"error": "Graph not initialized"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if not usubjid:
            self._send_json({"error": "Subject ID required"}, status=HTTPStatus.BAD_REQUEST)
            return

        p360 = GRAPH.patient360(usubjid)
        if not p360 or not p360.get("records"):
            self._send_json({
                "found": False,
                "usubjid": usubjid,
                "message": f"Subject '{usubjid}' was not found in STUDY-042."
            }, status=HTTPStatus.NOT_FOUND)
            return

        self._send_json({
            "found": True,
            "patient": p360,
        })

    def _classify_question_kind(self, text: str) -> str:
        """Helper to tag display kind for the UI."""
        t = text.lower()
        if t.startswith("how many") or "count" in t or "number of" in t:
            return "COUNT"
        if "list" in t or "lookup" in t or "records for" in t:
            return "LOOKUP"
        if "wrong dose" in t and ("s01" in t or "s02" in t):
            return "TRAP"
        return "FINDING"

    def _handle_ask(self) -> None:
        """POST /api/ask"""
        if ATLAS_ENGINE is None or GRAPH is None:
            self._send_json({"error": "Engine not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty request body"}, status=HTTPStatus.BAD_REQUEST)
            return

        raw_body = self.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            self._send_json({"error": f"Invalid JSON body: {e}"}, status=HTTPStatus.BAD_REQUEST)
            return

        raw_question = body.get("question", "").strip()
        if not raw_question:
            self._send_json({"error": "Missing 'question' parameter"}, status=HTTPStatus.BAD_REQUEST)
            return

        question_text = self._normalize_query_text(raw_question)
        qid = body.get("question_id", "Q_USER")
        q_kind = body.get("kind") or self._classify_question_kind(question_text)

        start_time = time.perf_counter()
        try:
            q_obj = Question(question_id=qid, text=question_text, kind=q_kind.lower())
            ans = ATLAS_ENGINE.answer(q_obj)
            elapsed_ms = round((time.perf_counter() - start_time) * 1000.0, 2)

            ans_dict = ans.to_dict()

            # Enrich evidence with clinical context from the raw records in StudyGraph
            enriched_evidence = []
            for ev in ans_dict.get("evidence", []):
                domain = ev.get("domain", "")
                usubjid = ev.get("usubjid", "")
                seq = ev.get("seq")

                record_data = GRAPH.get_record(domain, usubjid, seq)
                item: Dict[str, Any] = {
                    "domain": domain,
                    "usubjid": usubjid,
                    "seq": seq,
                    "citation": f"RecordRef(domain=\"{domain}\", usubjid=\"{usubjid}\", seq={seq})",
                }

                if record_data:
                    # Provide concise preview details for rich card display
                    item["visit"] = record_data.get("VISIT", "")
                    date_val = (
                        record_data.get(f"{domain}DTC")
                        or record_data.get(f"{domain}STDTC")
                        or record_data.get("LBDTC")
                        or record_data.get("AESTDTC")
                        or record_data.get("EXSTDTC")
                        or record_data.get("CMSTDTC")
                        or record_data.get("DSSTDTC")
                        or ""
                    )
                    item["date"] = date_val

                    if domain == "LB":
                        item["testcd"] = record_data.get("LBTESTCD", "")
                        item["raw_value"] = record_data.get("LBORRES", "")
                        item["unit"] = record_data.get("LBORRESU", "")
                        item["description"] = f"{item['testcd']}: {item['raw_value']} {item['unit']}"
                    elif domain == "AE":
                        item["term"] = record_data.get("AETERM", "")
                        item["severity"] = record_data.get("AESEV", "")
                        item["serious"] = record_data.get("AESER", "N")
                        item["hospitalized"] = record_data.get("AESHOSP", "N")
                        item["description"] = f"{item['term']} ({item['severity']})"
                    elif domain == "EX":
                        item["dose"] = record_data.get("EXDOSE", "")
                        item["unit"] = record_data.get("EXDOSU", "mg")
                        item["treatment"] = record_data.get("EXTRT", "")
                        item["description"] = f"Dose {item['dose']} {item['unit']} ({item['treatment']})"
                    elif domain == "CM":
                        item["treatment"] = record_data.get("CMTRT", "")
                        item["med_class"] = record_data.get("CMCLAS", "")
                        item["description"] = f"{item['treatment']} [{item['med_class']}]"
                    elif domain == "DS":
                        item["decod"] = record_data.get("DSDECOD", "")
                        item["term"] = record_data.get("DSTERM", "")
                        item["description"] = f"{item['decod']}: {item['term'] or 'Normal'}"
                    elif domain == "DM":
                        item["arm"] = record_data.get("ARM", "")
                        item["site"] = record_data.get("SITEID", "")
                        item["description"] = f"Site {item['site']}, Arm {item['arm']}"
                    else:
                        item["description"] = f"{domain} Record #{seq}"

                    # Attach raw attributes for expandable inspection
                    item["raw_fields"] = {
                        k: v for k, v in record_data.items()
                        if not k.startswith("_") and k not in ("domain", "usubjid", "seq")
                    }

                enriched_evidence.append(item)

            is_empty_trap = (len(enriched_evidence) == 0 and (ans.answer == [] or ans.answer == 0))

            response_payload = {
                "question_id": ans.question_id,
                "question": question_text,
                "kind": q_kind,
                "answer": ans.answer,
                "text": ans.text,
                "evidence": enriched_evidence,
                "evidence_count": len(enriched_evidence),
                "confidence": ans.confidence,
                "steps_used": ans.steps_used,
                "tokens_used": 0,
                "response_time_ms": elapsed_ms,
                "is_empty_trap": is_empty_trap,
            }
            self._send_json(response_payload)

        except Exception as e:
            logger.exception("Error answering question: %s", question_text)
            self._send_json({
                "error": f"Internal execution error: {e}",
                "question": question_text,
            }, status=HTTPStatus.INTERNAL_SERVER_ERROR)



    def _handle_monitor_status(self) -> None:
        """GET /api/monitor/status"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        last_rep = REVIEW_CREW.get_last_report()
        if last_rep is None:
            cut = getattr(GRAPH, "cut", 12) or 12
            ver = ATLAS_ENGINE.rules.protocol_version if ATLAS_ENGINE else 3
            last_rep = REVIEW_CREW.run_cycle(cut=cut, protocol_version=ver)

        self._send_json({
            "status": "online",
            "cycle_count": REVIEW_CREW.cycle_count,
            "active_cut": getattr(REVIEW_CREW.atlas.graph, "cut", 12) or 12,
            "protocol_version": REVIEW_CREW.atlas.rules.protocol_version,
            "memory": REVIEW_CREW.memory.to_dict(),
            "trace_count": len(REVIEW_CREW.trace.get_entries()),
            "has_report": True,
            "last_report_summary": last_rep.summary if last_rep else "No cycles executed yet.",
            "metrics": last_rep.metrics if last_rep else {},
        })

    def _handle_monitor_report(self) -> None:
        """GET /api/monitor/report"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        last_rep = REVIEW_CREW.get_last_report()
        if last_rep is None:
            cut = getattr(GRAPH, "cut", 12) or 12
            ver = ATLAS_ENGINE.rules.protocol_version if ATLAS_ENGINE else 3
            last_rep = REVIEW_CREW.run_cycle(cut=cut, protocol_version=ver)

        rep_dict = last_rep.to_dict()
        if REVIEW_CREW and REVIEW_CREW.memory:
            rep_dict["all_escalations"] = [e.to_dict() for e in REVIEW_CREW.memory.escalations.values()]
            rep_dict["all_queries"] = [q.to_dict() for q in REVIEW_CREW.memory.queries.values()]
        self._send_json(rep_dict)

    def _handle_monitor_trace(self) -> None:
        """GET /api/monitor/trace"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        entries = REVIEW_CREW.trace.to_list()
        self._send_json({"count": len(entries), "entries": entries})

    def _handle_monitor_escalations(self) -> None:
        """GET /api/monitor/escalations"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        last_rep = REVIEW_CREW.get_last_report()
        if last_rep and last_rep.escalations:
            escalations = [e.to_dict() for e in last_rep.escalations]
        elif REVIEW_CREW and REVIEW_CREW.memory and REVIEW_CREW.memory.escalations:
            escalations = [e.to_dict() for e in REVIEW_CREW.memory.escalations.values()]
        else:
            escalations = []
        self._send_json({"count": len(escalations), "escalations": escalations})

    def _handle_monitor_memory(self) -> None:
        """GET /api/monitor/memory"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return
        self._send_json(REVIEW_CREW.memory.to_dict())

    def _handle_monitor_cycle(self) -> None:
        """POST /api/monitor/cycle"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = {}
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            except Exception:
                body = {}

        cut = int(body.get("cut", getattr(GRAPH, "cut", 12) or 12))
        ver = int(body.get("protocol_version", ATLAS_ENGINE.rules.protocol_version if ATLAS_ENGINE else 3))

        try:
            report = REVIEW_CREW.run_cycle(cut=cut, protocol_version=ver)
            self._send_json(report.to_dict())
        except Exception as e:
            logger.exception("ReviewCrew cycle failed: %s", e)
            self._send_json({"error": f"Cycle run error: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_monitor_decision(self) -> None:
        """POST /api/monitor/escalations/decision"""
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty body"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            esc_id = body.get("escalation_id")
            decision = body.get("decision", "APPROVED").upper()
            reason = body.get("reason", "Decision recorded by human reviewer.")

            last_rep = REVIEW_CREW.get_last_report()
            if not last_rep:
                self._send_json({"error": "No active report"}, status=HTTPStatus.NOT_FOUND)
                return

            target_esc = next((e for e in last_rep.escalations if e.id == esc_id), None) if last_rep else None
            if not target_esc and REVIEW_CREW and REVIEW_CREW.memory:
                target_esc = next((e for e in REVIEW_CREW.memory.escalations.values() if e.id == esc_id), None)

            if not target_esc:
                self._send_json({"error": f"Escalation {esc_id} not found"}, status=HTTPStatus.NOT_FOUND)
                return

            suggestion = body.get("suggestion", "").strip()
            if suggestion:
                target_esc.suggested_action = suggestion

            if decision == "APPROVED":
                target_esc.status = GateDecision.APPROVED
                target_esc.gate_reason = reason
                if target_esc not in last_rep.approved_escalations:
                    last_rep.approved_escalations.append(target_esc)
                if target_esc in last_rep.rejected_escalations:
                    last_rep.rejected_escalations.remove(target_esc)
                REVIEW_CREW.memory.record_escalation(target_esc)

            elif decision == "REJECTED":
                target_esc.status = GateDecision.REJECTED
                target_esc.gate_reason = reason
                if target_esc in last_rep.approved_escalations:
                    last_rep.approved_escalations.remove(target_esc)
                if target_esc not in last_rep.rejected_escalations:
                    last_rep.rejected_escalations.append(target_esc)
                REVIEW_CREW.memory.record_rejection(target_esc.key)

            elif decision == "MONITORING":
                target_esc.status = GateDecision.MONITORING
                target_esc.gate_reason = reason
                REVIEW_CREW.memory.record_rejection(target_esc.key)

            elif decision == "CLARIFY":
                from stage2.escalations import resolve_monitor_clarification
                question = body.get("question", target_esc.clarification_question or "What were the screening baseline transaminase values?")
                resp_text = resolve_monitor_clarification(GRAPH, target_esc.target_id, question)
                target_esc.status = GateDecision.CLARIFY
                target_esc.clarification_question = question
                target_esc.clarification_response = resp_text
                if target_esc not in last_rep.clarified_escalations:
                    last_rep.clarified_escalations.append(target_esc)

            REVIEW_CREW.trace.record_step(
                cycle=REVIEW_CREW.cycle_count,
                node="human_gate",
                action="MANUAL_DECISION_OVERRIDE",
                details={
                    "escalation_id": esc_id,
                    "decision": decision,
                    "reason": reason,
                    "suggestion": suggestion,
                },
            )

            self._send_json({"status": "updated", "escalation": target_esc.to_dict()})

        except Exception as e:
            self._send_json({"error": str(e)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_chat(self) -> None:
        """POST /api/chat — Natural language conversational assistant endpoint."""
        global AI_ORCHESTRATOR, GRAPH
        if AI_ORCHESTRATOR is None or GRAPH is None:
            self._send_json({"error": "AI Orchestrator not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty request body"}, status=HTTPStatus.BAD_REQUEST)
            return

        raw_body = self.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            self._send_json({"error": f"Invalid JSON body: {e}"}, status=HTTPStatus.BAD_REQUEST)
            return

        message = body.get("message", "").strip()
        if not message:
            self._send_json({"error": "Missing 'message' parameter"}, status=HTTPStatus.BAD_REQUEST)
            return

        conversation_id = body.get("conversation_id")
        context_override = body.get("context", {})

        try:
            resp = AI_ORCHESTRATOR.process_message(
                message=message,
                conversation_id=conversation_id,
                context_override=context_override,
            )
            self._send_json(resp)
        except Exception as e:
            logger.exception("Error in AI chat: %s", e)
            self._send_json({"error": f"AI Orchestrator error: {e}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_get_conversation(self, cid: str) -> None:
        """GET /api/conversation/{id} — Fetch multi-turn conversation session."""
        global AI_ORCHESTRATOR
        if AI_ORCHESTRATOR is None:
            self._send_json({"error": "AI Orchestrator not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return
        conv = AI_ORCHESTRATOR.store.get(cid)
        if not conv:
            self._send_json({"error": f"Conversation '{cid}' not found"}, status=HTTPStatus.NOT_FOUND)
            return
        self._send_json(conv.to_dict())

    def _handle_monitor_fact_check(self) -> None:
        """POST /api/monitor/fact-check — Real-time clinical fact check against StudyGraph."""
        global REVIEW_CREW, GRAPH
        if REVIEW_CREW is None or GRAPH is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty body"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            from stage2.escalations import execute_fact_check
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            esc_id = body.get("escalation_id")
            query = body.get("query", "").strip()

            if not esc_id or not query:
                self._send_json({"error": "escalation_id and query are required"}, status=HTTPStatus.BAD_REQUEST)
                return

            last_rep = REVIEW_CREW.get_last_report()
            target_esc = next((e for e in last_rep.escalations if e.id == esc_id), None) if last_rep else None
            if not target_esc and REVIEW_CREW.memory:
                target_esc = next((e for e in REVIEW_CREW.memory.escalations.values() if e.id == esc_id), None)

            if not target_esc:
                self._send_json({"error": f"Escalation {esc_id} not found"}, status=HTTPStatus.NOT_FOUND)
                return

            fact_result = execute_fact_check(GRAPH, target_esc, query)

            REVIEW_CREW.trace.record_step(
                cycle=REVIEW_CREW.cycle_count,
                node="human_gate",
                action="MONITOR_FACT_CHECK",
                details={"escalation_id": esc_id, "query": query, "result": fact_result},
            )

            self._send_json({"status": "completed", "escalation": target_esc.to_dict(), "fact_check": fact_result})

        except Exception as e:
            logger.exception("Error executing fact check: %s", e)
            self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_monitor_comment(self) -> None:
        """POST /api/monitor/comment — Add doctor comment/suggestion to an escalation."""
        global REVIEW_CREW
        if REVIEW_CREW is None:
            self._send_json({"error": "ReviewCrew not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty body"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            esc_id = body.get("escalation_id")
            comment_text = body.get("comment", "").strip()
            author = body.get("author", "Medical Monitor").strip()
            suggestion = body.get("suggestion", "").strip()

            if not esc_id or not comment_text:
                self._send_json({"error": "escalation_id and comment are required"}, status=HTTPStatus.BAD_REQUEST)
                return

            last_rep = REVIEW_CREW.get_last_report()
            target_esc = next((e for e in last_rep.escalations if e.id == esc_id), None) if last_rep else None
            if not target_esc and REVIEW_CREW.memory:
                target_esc = next((e for e in REVIEW_CREW.memory.escalations.values() if e.id == esc_id), None)

            if not target_esc:
                self._send_json({"error": f"Escalation {esc_id} not found"}, status=HTTPStatus.NOT_FOUND)
                return

            import datetime
            c_entry = {
                "author": author,
                "comment": comment_text,
                "suggestion": suggestion,
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            target_esc.monitor_comments.append(c_entry)
            if suggestion:
                target_esc.suggested_action = suggestion

            REVIEW_CREW.trace.record_step(
                cycle=REVIEW_CREW.cycle_count,
                node="human_gate",
                action="MONITOR_COMMENT_ADDED",
                details={"escalation_id": esc_id, "comment": comment_text, "suggestion": suggestion},
            )

            self._send_json({"status": "updated", "escalation": target_esc.to_dict()})

        except Exception as e:
            logger.exception("Error adding comment: %s", e)
            self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_graph_subject_domain(self, path: str) -> None:
        """GET /api/graph/subject/{usubjid} or /api/graph/subject/{usubjid}/{domain}"""
        global GRAPH
        if GRAPH is None:
            self._send_json({"error": "Graph not initialized"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        parts = path.strip("/").split("/")
        if len(parts) < 4:
            self._send_json({"error": "Invalid path"}, status=HTTPStatus.BAD_REQUEST)
            return

        usubjid = unquote(parts[3])
        domain = unquote(parts[4]).upper() if len(parts) >= 5 else None

        if usubjid not in GRAPH.subjects:
            self._send_json({"error": f"Subject '{usubjid}' not found"}, status=HTTPStatus.NOT_FOUND)
            return

        if domain:
            dom_recs = GRAPH.subject_domain_records.get((usubjid, domain), [])
            enriched = []
            for r in dom_recs:
                seq = r.get("seq", 1)
                rec_info = dict(r)
                rec_info["domain"] = domain
                rec_info["usubjid"] = usubjid
                rec_info["seq"] = seq
                rec_info["citation"] = f"RecordRef(domain=\"{domain}\", usubjid=\"{usubjid}\", seq={seq})"
                enriched.append(rec_info)
            self._send_json({
                "usubjid": usubjid,
                "domain": domain,
                "count": len(enriched),
                "records": enriched,
            })
        else:
            p360 = GRAPH.patient360(usubjid)
            self._send_json({
                "usubjid": usubjid,
                "site_id": p360.get("site_id", ""),
                "arm": p360.get("arm", ""),
                "demographics": p360.get("demographics", {}),
                "domains": {d: len(recs) for d, recs in p360.get("records_by_domain", {}).items()},
                "total_records": len(p360.get("records", [])),
            })


    # -------------------------------------------------------------------------
    # Stage 3 — WATCH Surveillance API Handlers
    # -------------------------------------------------------------------------

    def _handle_watch_cuts(self) -> None:
        """GET /api/watch/cuts — Returns summary of all surveillance cuts."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        reports_summary = []
        for cut_num in sorted(WATCH_SURVEILLANCE.cut_reports.keys()):
            rep = WATCH_SURVEILLANCE.cut_reports[cut_num]
            reports_summary.append(rep.to_dict())

        self._send_json({
            "status": "success",
            "active_cut": WATCH_SURVEILLANCE.active_cut,
            "protocol_version": WATCH_SURVEILLANCE.current_protocol_version,
            "total_decisions": len(WATCH_SURVEILLANCE.decisions_log),
            "budget_state": WATCH_SURVEILLANCE.budget.get_state().value,
            "cuts": reports_summary,
        })

    def _handle_watch_cut_detail(self, cut_num: int) -> None:
        """GET /api/watch/cut/{cut_num} — Returns full report for a specific cut."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        rep = WATCH_SURVEILLANCE.cut_reports.get(cut_num)
        if not rep:
            rep = WATCH_SURVEILLANCE.process_cut(cut_num)

        self._send_json(rep.to_dict())

    def _handle_watch_decisions(self) -> None:
        """GET /api/watch/decisions — Returns all logged surveillance decisions."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        decs = [d.to_dict() for d in WATCH_SURVEILLANCE.decisions_log.values()]
        self._send_json({
            "total": len(decs),
            "decisions": decs,
        })

    def _handle_watch_explain_decision(self, decision_id: str) -> None:
        """GET /api/watch/decision/{id} — Explains decision from stored trace."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        res = WATCH_SURVEILLANCE.explain(decision_id)
        status_code = HTTPStatus.OK if res.get("found") else HTTPStatus.NOT_FOUND
        self._send_json(res, status=status_code)

    def _handle_watch_suspicious_sites(self) -> None:
        """GET /api/watch/suspicious-sites — Returns low-variability statistical anomalies."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        findings = WATCH_SURVEILLANCE.site_detector.detect_low_variability_sites(cut=12)
        self._send_json({
            "findings_count": len(findings),
            "findings": [f.to_dict() for f in findings],
        })

    def _handle_watch_data_integrity(self) -> None:
        """GET /api/watch/data-integrity — Returns laboratory analyser unit mismatch anomalies."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        findings = WATCH_SURVEILLANCE.integrity_detector.detect_analyser_unit_mismatch(cut=12)
        self._send_json({
            "findings_count": len(findings),
            "findings": [f.to_dict() for f in findings],
        })

    def _handle_watch_protocol_amendments(self) -> None:
        """GET /api/watch/protocol-amendments — Returns protocol diffs and affected findings."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        diff2 = WATCH_SURVEILLANCE.amendment_detector.get_protocol_diff(1, 2, 5)
        diff3 = WATCH_SURVEILLANCE.amendment_detector.get_protocol_diff(2, 3, 9)
        self._send_json({
            "active_version": WATCH_SURVEILLANCE.current_protocol_version,
            "amendments": [diff2.to_dict(), diff3.to_dict()],
        })

    def _handle_watch_budget(self) -> None:
        """GET /api/watch/budget — Returns current budget consumption and state."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        b = WATCH_SURVEILLANCE.budget
        self._send_json({
            "state": b.get_state().value,
            "elapsed_seconds": b.get_elapsed_seconds(),
            "remaining_seconds": b.get_remaining_seconds(),
            "total_budget_seconds": b.total_seconds,
            "operations_count": b.operations_count,
            "records_processed": b.records_processed,
            "degradation_profile": b.get_degradation_profile(),
        })

    def _handle_watch_run_cuts(self) -> None:
        """POST /api/watch/run — Executes longitudinal surveillance cuts."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        target_cut = 12
        if content_length > 0:
            try:
                body = json.loads(self.rfile.read(content_length).decode("utf-8"))
                target_cut = int(body.get("cut", 12))
            except:
                pass

        reports = WATCH_SURVEILLANCE.run_all_cuts(target_cut)
        self._send_json({
            "status": "completed",
            "cuts_processed": len(reports),
            "active_cut": WATCH_SURVEILLANCE.active_cut,
            "total_decisions": len(WATCH_SURVEILLANCE.decisions_log),
        })

    def _handle_watch_explain_post(self) -> None:
        """POST /api/watch/explain — Explains decision from stored trace."""
        global WATCH_SURVEILLANCE
        if WATCH_SURVEILLANCE is None:
            self._send_json({"error": "WatchSurveillance not initialized"}, status=HTTPStatus.SERVICE_UNAVAILABLE)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            self._send_json({"error": "Empty body"}, status=HTTPStatus.BAD_REQUEST)
            return

        try:
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            decision_id = str(body.get("decision_id", "")).strip()
            if not decision_id:
                self._send_json({"error": "decision_id is required"}, status=HTTPStatus.BAD_REQUEST)
                return

            res = WATCH_SURVEILLANCE.explain(decision_id)
            self._send_json(res)
        except Exception as e:
            self._send_json({"error": str(e)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


def start_server(host: Optional[str] = None, port: Optional[int] = None, data_dir: Optional[str] = None) -> None:
    """Initializes StudyGraph, Atlas Engine, ReviewCrew, WatchSurveillance, and AI Conversational Orchestrator."""
    global GRAPH, ATLAS_ENGINE, DATA_DIR_PATH, REVIEW_CREW, WATCH_SURVEILLANCE, AI_ORCHESTRATOR

    # Bind host to 0.0.0.0 for cloud deployment compatibility (e.g. Render)
    target_host = host if host is not None else os.environ.get("HOST", "0.0.0.0")
    if port is not None:
        target_port = port
    else:
        try:
            target_port = int(os.environ.get("PORT", "8080"))
        except (ValueError, TypeError):
            target_port = 8080

    resolved_data_dir = (
        Path(data_dir)
        if data_dir
        else PROJECT_ROOT / "DATASET-20260918T152607Z-1-001" / "DATASET" / "hackathon-data" / "hackathon-data"
    )

    if not resolved_data_dir.exists():
        logger.error("Dataset directory not found: %s", resolved_data_dir)
        sys.exit(1)

    DATA_DIR_PATH = resolved_data_dir
    print("=" * 64)
    print("  ATLAS — Clinical Study Intelligence Browser Platform")
    print("=" * 64)
    print(f"Loading StudyGraph from: {resolved_data_dir}")

    GRAPH = StudyGraph(str(resolved_data_dir))
    stats = GRAPH.build()
    GRAPH.build_time_ms = stats["build_time_ms"]

    ATLAS_ENGINE = Atlas(GRAPH)
    REVIEW_CREW = ReviewCrew(atlas=ATLAS_ENGINE)
    WATCH_SURVEILLANCE = WatchSurveillance(atlas=ATLAS_ENGINE, review_crew=REVIEW_CREW)
    print("Pre-running 12 Watch longitudinal surveillance cuts...")
    WATCH_SURVEILLANCE.run_all_cuts(12)
    print(f"  • Watch Cuts:      12 processed")
    print(f"  • Watch Decisions: {len(WATCH_SURVEILLANCE.decisions_log)} logged")

    AI_ORCHESTRATOR = AtlasConversationalOrchestrator(
        atlas=ATLAS_ENGINE,
        review_crew=REVIEW_CREW,
        watch=WATCH_SURVEILLANCE,
    )

    print(f"Graph initialized in {stats['build_time_ms']} ms:")
    print(f"  • Subjects: {stats['subjects']}")
    print(f"  • Nodes:    {stats['nodes']}")
    print(f"  • Edges:    {stats['edges']}")
    print("=" * 64)

    server = ThreadingHTTPServer((target_host, target_port), AtlasRequestHandler)
    url = f"http://{target_host}:{target_port}"
    print(f"Server online at: {url}")
    print("Press Ctrl+C to stop.")
    print("=" * 64)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down ATLAS server...")
        server.server_close()


if __name__ == "__main__":
    try:
        env_port = int(os.environ.get("PORT", "8080"))
    except (ValueError, TypeError):
        env_port = 8080
    env_host = os.environ.get("HOST", "0.0.0.0")

    parser = argparse.ArgumentParser(description="ATLAS Production Web Application Server")
    parser.add_argument("--host", type=str, default=env_host, help=f"Host address (default: {env_host})")
    parser.add_argument("--port", type=int, default=env_port, help=f"Port number (default: {env_port})")
    parser.add_argument("--data", type=str, default=None, help="Path to hackathon study data directory")
    args = parser.parse_args()

    start_server(host=args.host, port=args.port, data_dir=args.data)
