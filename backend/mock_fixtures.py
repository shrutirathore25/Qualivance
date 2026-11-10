"""
mock_fixtures.py - deterministic fake AI output for testing WITHOUT calling Groq.

Everything here is fictional and mirrors the frontend demo data. Later phases use
MOCK_DRAFT to test the API, the database and the UI without spending model credits.
"""
from schemas import InvestigationDraft

MOCK_DRAFT_DICT = {
    "product_name": None,                       # absent in the source -> stays empty
    "batch_number": "B-DEMO-014",
    "incident_date": None,
    "deviation_description": "Moisture result exceeds the stated maximum specification.",
    "observed_result": "1.2%",
    "specification": "Maximum 0.5%",
    "immediate_containment": None,
    "investigation_method": "5_whys",
    "whys": [
        {"question": "Why was the moisture result out of specification?",
         "answer": "The reported result (1.2%) is above the stated maximum (0.5%).", "status": "answered"},
        {"question": "Why was residual moisture higher than allowed?", "answer": None, "status": "unanswered"},
    ],
    "potential_root_causes": [
        {"hypothesis": "Drying process did not remove sufficient moisture",
         "rationale": "The result is above the limit, but the report does not establish why.",
         "evidence_needed": ["Dryer time/temperature logs", "Equipment maintenance records"],
         "status": "unverified"},
    ],
    "contributing_factors": [],
    "missing_evidence": ["Dryer logs", "Moisture test method and calibration records"],
    "corrective_actions": [
        {"type": "corrective", "description": "Review dryer logs for this batch with the responsible qualified person.",
         "rationale": "Needed to confirm or reject the drying hypothesis.",
         "linked_cause": "Drying process did not remove sufficient moisture",
         "verification": "Documented review of logs", "status": "draft"},
    ],
    "preventive_actions": [
        {"type": "preventive", "description": "Consider adding a drying-endpoint check to the batch record.",
         "rationale": "Could reduce repeat occurrences if the drying hypothesis is confirmed.",
         "linked_cause": "Drying process did not remove sufficient moisture",
         "verification": "Moisture trend over the next batches", "status": "draft"},
    ],
    "uncertainties": ["Cause not established from the supplied text."],
    "source_facts": [
        {"field": "observed_result", "value": "1.2%",
         "source_quote": "the moisture result was recorded as 1.2%", "confidence": "source_supported"},
    ],
    "status": "Ready for Review",
    "source_type": "text",
    "is_mock": True,
}


def get_mock_draft() -> InvestigationDraft:
    return InvestigationDraft.model_validate(MOCK_DRAFT_DICT)


# ---------------------------------------------------------------------------
# Canned answers used by MockLLM (one per workflow task). Fictional data only.
# ---------------------------------------------------------------------------
import re as _re


def _mock_classify(user: str) -> dict:
    m = _re.search(r"<user_message>\n(.*?)\n</user_message>", user, _re.S)
    msg = (m.group(1) if m else "").strip()
    if len(msg) > 400:
        return {"intent": "new_document"}
    if _re.search(r"(?i)\b(batch number|product|incident date|date|result|specification|classification)\b.*\b(is|are|should be|=)\b", msg):
        return {"intent": "correction"}
    return {"intent": "question"}


def _mock_correction(user: str) -> dict:
    m = _re.search(r"<user_message>\n(.*?)\n</user_message>", user, _re.S)
    msg = m.group(1) if m else ""
    changes = {}
    b = _re.search(r"(?i)batch number (?:is|=|should be)\s*([A-Za-z0-9\-]+)", msg)
    if b:
        changes["batch_number"] = b.group(1)
    r = _re.search(r"(?i)(?:observed )?result (?:is|=|should be)\s*([0-9.]+\s*%?)", msg)
    if r:
        changes["observed_result"] = r.group(1).strip()
    return {"changes": changes}


MOCK_LLM_RESPONSES = {
    "classify": _mock_classify,
    "extract": {
        "product_name": None,
        "batch_number": "B-DEMO-014",
        "incident_date": None,
        "deviation_description": "Moisture result exceeds the stated maximum specification.",
        "observed_result": "1.2%",
        "specification": "Maximum 0.5%",
        "immediate_containment": None,
        "deviation_id": None,
        "classification": None,
        "area_equipment": None,
        "impact_assessment": None,
        "immediate_action": None,
        "effectiveness_check": None,
        "source_facts": [
            {"field": "observed_result", "value": "1.2%",
             "source_quote": "the moisture result was recorded as 1.2%"},
        ],
    },
    "validate_evidence": {
        "missing_evidence": ["Dryer time/temperature logs", "Moisture test method and calibration records"],
        "contradictions": [],
    },
    "analyze": {
        "whys": MOCK_DRAFT_DICT["whys"],
        "potential_root_causes": [
            {"hypothesis": "Drying process did not remove sufficient moisture",
             "rationale": "The result is above the limit, but the report does not establish why.",
             "evidence_needed": ["Dryer time/temperature logs", "Equipment maintenance records"]},
        ],
        "contributing_factors": [],
        "uncertainties": ["Cause not established from the supplied text."],
    },
    "capa": {
        "corrective_actions": [
            {"description": "Review dryer logs for this batch with the responsible qualified person.",
             "rationale": "Needed to confirm or reject the drying hypothesis.",
             "linked_cause": "Drying process did not remove sufficient moisture",
             "verification": "Documented review of logs"}],
        "preventive_actions": [
            {"description": "Consider adding a drying-endpoint check to the batch record.",
             "rationale": "Could reduce repeat occurrences if the drying hypothesis is confirmed.",
             "linked_cause": "Drying process did not remove sufficient moisture",
             "verification": "Moisture trend over the next batches"}],
    },
    "correction": _mock_correction,
    "question": {"answer": "This is a fixed demo answer. The suggested causes are unverified until a qualified person reviews them."},
}
