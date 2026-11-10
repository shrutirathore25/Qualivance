"""
ai_workflow.py - the LangGraph workflow behind POST /api/analyze.

                     +--> extract_incident --> (enough info?) --yes--> validate_evidence
 START -> classify --+                                  |                    |
                     |                                  no                   v
                     |                                  |             analyze_root_cause
                     |                                  |                    |
                     |                                  |                    v
                     |                                  |             recommend_capa
                     |                                  v                    |
                     |                            validate_output <----------+
                     |                                  |
                     |                                  v
                     |                            prepare_review --> END
                     +--> apply_correction --> END      (changes only the fields named)
                     +--> answer_question  --> END

The LLM suggests; this code checks. Safeguards that do not depend on the prompt:
  * grounding   : identifiers, dates and numbers must appear in the source, else they are blanked
  * 5 Whys      : once a step is unanswered, every later step is forced to unanswered
  * causes      : always status "unverified"
  * CAPA        : always "draft"; items that tell people to release/override/bypass are dropped
  * validation  : the final draft must pass the Pydantic schema; bad items are discarded
"""
import re
from typing import Any, Optional, TypedDict, Union

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

import prompts
from llm import get_llm
from schemas import (Action, AnalyzeResponse, ContributingFactor, InvestigationDraft,
                     PotentialRootCause, SourceFact, WhyStep)

FORM_FIELDS = [
    "product_name", "batch_number", "incident_date", "deviation_description", "observed_result",
    "specification", "immediate_containment", "deviation_id", "classification", "area_equipment",
    "impact_assessment", "immediate_action", "effectiveness_check",
]
LABELS = {f: f.replace("_", " ") for f in FORM_FIELDS}
CLASSIFICATIONS = {"minor", "major", "critical"}
INTENTS = {"new_document", "correction", "question"}
MAX_WHYS, MAX_CAUSES, MAX_ACTIONS, MAX_LIST = 5, 6, 6, 15


class State(TypedDict, total=False):
    text: str
    source_type: Optional[str]
    current_draft: Optional[dict]
    intent: str
    extraction: dict
    source_facts: list
    warnings: list
    sufficient: bool
    missing_evidence: list
    contradictions: list
    analysis: dict
    capa: dict
    draft: Optional[dict]
    reply: str
    changed_fields: dict


# ------------------------------------------------------------------ helpers
def _s(v: Any) -> Optional[str]:
    """Coerce a model value to a clean string or None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str) and v.strip() and v.strip().lower() not in {"null", "none", "n/a", "unknown"}:
        return v.strip()
    return None


def _str_list(v: Any, cap: int = MAX_LIST) -> list[str]:
    out, seen = [], set()
    for item in v if isinstance(v, list) else []:
        t = _s(item)
        if t and t.lower() not in seen:
            seen.add(t.lower())
            out.append(t)
    return out[:cap]


def _nospace(t: str) -> str:
    return re.sub(r"\s+", "", t).lower()


_NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _grounded(field: str, value: str, source: str) -> bool:
    """Is this value really in the source text?"""
    if field == "classification":
        return re.search(rf"\b{re.escape(value)}\b", source, re.IGNORECASE) is not None
    if field in {"observed_result", "specification", "incident_date"}:
        nums = _NUM.findall(value)
        if nums:
            src_nums = {n.replace(",", ".") for n in _NUM.findall(source)}
            return all(n.replace(",", ".") in src_nums for n in nums)
    return _nospace(value) in _nospace(source)


GROUNDED_FIELDS = ["product_name", "batch_number", "incident_date", "observed_result",
                   "specification", "deviation_id", "classification"]

FORBIDDEN = [
    r"\b(release|releasing|approve|approving|disposition)\b[^.]{0,60}\b(batch|lot|product)\b",
    r"\boverrid\w*\b[^.]{0,60}\b(spec\w*|limit|procedure)",
    r"\bbypass\w*",
    r"\b(waive|ignore)\b[^.]{0,40}\b(spec\w*|oos|limit)",
]
SAFE_CONTEXT = re.compile(r"\b(do not|don't|not|until|pending|before|hold|escalate)\b", re.IGNORECASE)


def _is_unsafe(text: str) -> bool:
    if SAFE_CONTEXT.search(text):
        return False
    return any(re.search(p, text, re.IGNORECASE) for p in FORBIDDEN)


def _has_content(draft: Optional[dict]) -> bool:
    return bool(draft) and any(draft.get(f) for f in FORM_FIELDS)


def _sufficient(f: dict) -> bool:
    core = f.get("deviation_description") or f.get("observed_result")
    filled = sum(1 for k in ("batch_number", "incident_date", "observed_result", "specification",
                             "deviation_description") if f.get(k))
    return bool(core) and filled >= 2


# --------------------------------------------------------------- graph builder
def build_graph(llm):
    SYS = prompts.SYSTEM_RULES

    def ask(task: str, user: str) -> dict:
        out = llm.complete_json(task, SYS, user)
        return out if isinstance(out, dict) else {}

    # 1 ----------------------------------------------------------------------
    def classify_message(state: State) -> dict:
        draft = state.get("current_draft")
        if not _has_content(draft):
            return {"intent": "new_document"}
        out = ask("classify", prompts.classify_user(state["text"], draft))
        intent = out.get("intent")
        if intent not in INTENTS:
            intent = "new_document" if len(state["text"]) > 800 else "question"
        return {"intent": intent}

    # 2 ----------------------------------------------------------------------
    def extract_incident(state: State) -> dict:
        text = state["text"]
        raw = ask("extract", prompts.extract_user(text))
        ext, warnings = {}, []
        for f in FORM_FIELDS:
            ext[f] = _s(raw.get(f))
        if ext["classification"]:
            ext["classification"] = ext["classification"].lower()
            if ext["classification"] not in CLASSIFICATIONS:
                ext["classification"] = None
        # grounding check: blank anything that is not actually in the source
        for f in GROUNDED_FIELDS:
            if ext.get(f) and not _grounded(f, ext[f], text):
                warnings.append(f"The {LABELS[f]} suggested by the AI was not found in the source, so it was left blank.")
                ext[f] = None
        facts = []
        for item in raw.get("source_facts") if isinstance(raw.get("source_facts"), list) else []:
            try:
                fact = SourceFact.model_validate(item)
            except ValidationError:
                continue
            if fact.source_quote and _nospace(fact.source_quote) not in _nospace(text):
                fact.source_quote, fact.confidence = None, "unclear"   # quote not verbatim
            facts.append(fact.model_dump())
        return {"extraction": ext, "source_facts": facts[:MAX_LIST], "warnings": warnings,
                "sufficient": _sufficient(ext)}

    # 3 ----------------------------------------------------------------------
    def validate_evidence(state: State) -> dict:
        out = ask("validate_evidence", prompts.evidence_user(state["text"], state["extraction"]))
        return {"missing_evidence": _str_list(out.get("missing_evidence")),
                "contradictions": _str_list(out.get("contradictions"), 8)}

    # 4 ----------------------------------------------------------------------
    def analyze_root_cause(state: State) -> dict:
        out = ask("analyze", prompts.analyze_user(state["text"], state["extraction"],
                                                  state.get("missing_evidence", [])))
        whys, broken = [], False
        for item in out.get("whys") if isinstance(out.get("whys"), list) else []:
            try:
                w = WhyStep.model_validate(item)
            except ValidationError:
                continue
            if broken or not w.answer:
                broken = True                      # never invent later answers
                w.answer, w.status = None, "unanswered"
            else:
                w.status = "answered"
            whys.append(w.model_dump())
            if len(whys) == MAX_WHYS:
                break
        causes, notes = [], []
        for item in out.get("potential_root_causes") if isinstance(out.get("potential_root_causes"), list) else []:
            try:
                c = PotentialRootCause.model_validate(item)
            except ValidationError:
                continue
            c.status = "unverified"               # a plausible cause is never confirmed by the AI
            c.evidence_needed = _str_list(c.evidence_needed, 8) or [
                "Records that would confirm or reject this hypothesis were not specified; add them during review."]
            causes.append(c.model_dump())
            if len(causes) == MAX_CAUSES:
                break
        factors = []
        for item in out.get("contributing_factors") if isinstance(out.get("contributing_factors"), list) else []:
            try:
                factors.append(ContributingFactor.model_validate(item).model_dump())
            except ValidationError:
                continue
        return {"analysis": {"whys": whys, "potential_root_causes": causes,
                             "contributing_factors": factors[:MAX_LIST],
                             "uncertainties": _str_list(out.get("uncertainties"))}}

    # 5 ----------------------------------------------------------------------
    def recommend_capa(state: State) -> dict:
        causes = state["analysis"]["potential_root_causes"]
        if not causes:
            return {"capa": {"corrective_actions": [], "preventive_actions": [], "dropped": 0}}
        out = ask("capa", prompts.capa_user(state["text"], [c["hypothesis"] for c in causes]))
        known = {c["hypothesis"].strip().lower(): c["hypothesis"] for c in causes}
        dropped, result = 0, {}
        for key, kind in (("corrective_actions", "corrective"), ("preventive_actions", "preventive")):
            items = []
            for item in out.get(key) if isinstance(out.get(key), list) else []:
                if not isinstance(item, dict):
                    continue
                item = {**item, "type": kind, "status": "draft"}      # type/status are set by code
                try:
                    a = Action.model_validate(item)
                except ValidationError:
                    continue
                if _is_unsafe(" ".join(filter(None, [a.description, a.rationale]))):
                    dropped += 1
                    continue
                a.linked_cause = known.get((a.linked_cause or "").strip().lower())   # None if not a real hypothesis
                items.append(a.model_dump())
                if len(items) == MAX_ACTIONS:
                    break
            result[key] = items
        result["dropped"] = dropped
        return {"capa": result}

    # 6 ----------------------------------------------------------------------
    def validate_output(state: State) -> dict:
        ext = state["extraction"]
        analysis = state.get("analysis") or {}
        capa = state.get("capa") or {}
        ran = bool(analysis)
        missing = list(state.get("missing_evidence", []))
        missing += [f"Conflicting information to resolve: {c}" for c in state.get("contradictions", [])]
        miss_keys = {m.lower().strip(" .") for m in missing}
        uncertainties = [u for u in analysis.get("uncertainties", [])
                         if u.lower().strip(" .") not in miss_keys] + list(state.get("warnings", []))
        if capa.get("dropped"):
            uncertainties.append(f"{capa['dropped']} suggested action(s) were removed because they conflicted with safety rules.")
        if not ran:
            missing.insert(0, "The source does not contain enough information to start an analysis. "
                              "Provide the batch, date, result, specification and what happened.")
            uncertainties.append("No root-cause analysis was attempted because the source text is insufficient.")
        data = {
            **ext,
            "investigation_method": "5_whys",
            "whys": analysis.get("whys", []),
            "potential_root_causes": analysis.get("potential_root_causes", []),
            "contributing_factors": analysis.get("contributing_factors", []),
            "missing_evidence": missing[:MAX_LIST + 8],
            "corrective_actions": capa.get("corrective_actions", []),
            "preventive_actions": capa.get("preventive_actions", []),
            "uncertainties": uncertainties[:MAX_LIST + 8],
            "source_facts": state.get("source_facts", []),
            "status": "Ready for Review" if ran else "Draft",
            "source_type": state.get("source_type"),
            "field_sources": {f: ("source" if ext.get(f) else "") for f in FORM_FIELDS},
            "is_mock": bool(getattr(llm, "is_mock", False)),
        }
        try:
            draft = InvestigationDraft.model_validate(data)
        except ValidationError:
            # Safe fallback: keep only the grounded form fields, discard the rest.
            safe = {**ext, "status": "Draft", "source_type": state.get("source_type"),
                    "field_sources": data["field_sources"], "is_mock": data["is_mock"],
                    "uncertainties": ["Some AI output was invalid and was discarded. Review and complete the form manually."]}
            draft = InvestigationDraft.model_validate(safe)
        return {"draft": draft.model_dump()}

    # 7 ----------------------------------------------------------------------
    def prepare_review(state: State) -> dict:
        d = state["draft"]
        filled = [LABELS[f] for f in FORM_FIELDS if d.get(f)]
        empty = [LABELS[f] for f in ("product_name", "batch_number", "incident_date", "observed_result", "specification")
                 if not d.get(f)]
        if not state.get("sufficient"):
            reply = ("I could not find enough information to start an investigation. "
                     + (f"I filled: {', '.join(filled)}. " if filled else "")
                     + "Please add the batch, date, result, specification and what happened.")
        else:
            n = len(d["potential_root_causes"])
            reply = (f"Report parsed. I filled {len(filled)} fields"
                     + (f" and left blank (not in the source): {', '.join(empty)}." if empty else ".")
                     + f" I drafted {n} possible cause(s), all unverified, and listed {len(d['missing_evidence'])} "
                       "item(s) of missing evidence. Everything is a suggestion for a qualified person to review.")
        return {"reply": reply}

    # 8 ----------------------------------------------------------------------
    def apply_correction(state: State) -> dict:
        cur = state["current_draft"]
        out = ask("correction", prompts.correction_user(state["text"], cur))
        raw = out.get("changes") if isinstance(out.get("changes"), dict) else {}
        changes, ignored = {}, []
        for field, value in raw.items():
            if field not in FORM_FIELDS:
                ignored.append(str(field)[:40])
                continue
            v = _s(value)
            if field == "classification" and v:
                v = v.lower()
                if v not in CLASSIFICATIONS:
                    ignored.append(field)
                    continue
            if v == _s(cur.get(field)):
                continue                                   # nothing actually changes
            changes[field] = v
        if not changes:
            return {"changed_fields": {}, "draft": None,
                    "reply": "I could not tell which field to change. Try, for example: \"the batch number is B-123\"."}
        sources = dict(cur.get("field_sources") or {})
        lines = []
        for f, v in changes.items():
            old = _s(cur.get(f))
            lines.append(f"{LABELS[f]}: {old or 'empty'} -> {v or 'cleared'}")
            sources[f] = "user"
        return {"changed_fields": changes, "draft": None,
                "reply": "Updated " + "; ".join(lines) + ". Nothing else was changed.",
                "current_draft": {**cur, **changes, "field_sources": sources}}

    # 9 ----------------------------------------------------------------------
    def answer_question(state: State) -> dict:
        out = ask("question", prompts.question_user(state["text"], state["current_draft"]))
        ans = _s(out.get("answer")) or "I could not find an answer in the current investigation."
        return {"reply": ans, "changed_fields": {}, "draft": None}

    # ---- wiring ------------------------------------------------------------
    g = StateGraph(State)
    for fn in (classify_message, extract_incident, validate_evidence, analyze_root_cause,
               recommend_capa, validate_output, prepare_review, apply_correction, answer_question):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "classify_message")
    g.add_conditional_edges("classify_message", lambda s: s["intent"], {
        "new_document": "extract_incident", "correction": "apply_correction", "question": "answer_question"})
    g.add_conditional_edges("extract_incident", lambda s: "ok" if s["sufficient"] else "thin", {
        "ok": "validate_evidence", "thin": "validate_output"})
    g.add_edge("validate_evidence", "analyze_root_cause")
    g.add_edge("analyze_root_cause", "recommend_capa")
    g.add_edge("recommend_capa", "validate_output")
    g.add_edge("validate_output", "prepare_review")
    g.add_edge("prepare_review", END)
    g.add_edge("apply_correction", END)
    g.add_edge("answer_question", END)
    return g.compile()


# ------------------------------------------------------------------ entry point
def run_workflow(text: str, source_type: Optional[str] = "text",
                 current_draft: Union[InvestigationDraft, dict, None] = None,
                 llm=None) -> AnalyzeResponse:
    """Run one message through the workflow. Raises llm.LLMError on provider problems
    (the API layer turns that into a clean error and keeps the user's input)."""
    llm = llm or get_llm()
    if isinstance(current_draft, InvestigationDraft):
        current_draft = current_draft.model_dump()
    final = build_graph(llm).invoke({"text": text, "source_type": source_type, "current_draft": current_draft})
    draft = InvestigationDraft.model_validate(final["draft"]) if final.get("draft") else None
    return AnalyzeResponse(intent=final["intent"], reply=final.get("reply", ""),
                           draft=draft, changed_fields=final.get("changed_fields") or {})
