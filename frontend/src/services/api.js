// The only file that talks to the backend. Also converts between the backend's
// snake_case draft and the Redux state used by the React form.
import { FORM_FIELDS } from "../features/investigationSlice";

// Not a secret: just the address of the local backend.
const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.code = code;
    this.status = status;
  }
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(BASE + path, options);
  } catch {
    throw new ApiError("network", "Cannot reach the backend. Check that it is running on port 8000.", 0);
  }
  let data = null;
  try { data = await res.json(); } catch { /* body was not JSON */ }
  if (!res.ok) {
    const message =
      data?.message || (typeof data?.detail === "string" ? data.detail : null) ||
      `The server returned an error (${res.status}).`;
    throw new ApiError(data?.code || "http_error", message, res.status);
  }
  return data;
}

const json = (method, body) => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});

// ---- API calls ---------------------------------------------------------
export function analyze({ text, sourceType, file, currentDraft }) {
  const fd = new FormData();
  if (file) {
    fd.append("file", file);
    fd.append("source_type", "pdf");
  } else {
    fd.append("text", text);
    fd.append("source_type", sourceType || "text");
  }
  if (currentDraft) fd.append("current_draft", JSON.stringify(currentDraft));
  return request("/api/analyze", { method: "POST", body: fd });
}
export const listInvestigations = () => request("/api/investigations");
export const getInvestigation = (id) => request(`/api/investigations/${id}`);
export const createInvestigation = (draft) => request("/api/investigations", json("POST", { draft }));
export const updateInvestigation = (id, draft) => request(`/api/investigations/${id}`, json("PUT", { draft }));

// ---- mappers -----------------------------------------------------------
// Backend draft -> Redux shape (used by applyAnalysis).
export function fromBackendDraft(d) {
  const sources = d.field_sources || {};
  const form = {};
  const fieldSources = {};
  FORM_FIELDS.forEach((f) => {
    const v = d[f] ?? "";
    form[f] = v;
    fieldSources[f] = !v ? "empty" : sources[f] === "user" ? "user" : "source";
  });
  return {
    form,
    fieldSources,
    investigationMethod: d.investigation_method ?? "5_whys",
    whys: d.whys ?? [],
    potentialCauses: d.potential_root_causes ?? [],
    missingEvidence: d.missing_evidence ?? [],
    correctiveActions: d.corrective_actions ?? [],
    preventiveActions: d.preventive_actions ?? [],
    uncertainties: d.uncertainties ?? [],
    sourceType: d.source_type ?? null,
    isMock: !!d.is_mock,
    status: d.status ?? "Ready for Review",
    extra: d, // the full backend draft, so fields the form does not show are not lost
  };
}

const filled = (s) => typeof s === "string" && s.trim() !== "";
const cleanStrings = (a) => (a || []).map((s) => (typeof s === "string" ? s.trim() : "")).filter(Boolean);

// Redux state -> backend draft. Half-added blank rows are dropped so they
// cannot make the save fail validation.
export function toBackendDraft(inv) {
  const form = {};
  FORM_FIELDS.forEach((f) => { form[f] = filled(inv.form[f]) ? inv.form[f].trim() : null; });
  const field_sources = {};
  FORM_FIELDS.forEach((f) => {
    if (form[f] && (inv.fieldSources[f] === "user" || inv.fieldSources[f] === "source")) {
      field_sources[f] = inv.fieldSources[f];
    }
  });
  const actions = (list, type) =>
    list.filter((a) => filled(a.description)).map((a) => ({ ...a, type, status: a.status || "draft" }));

  return {
    ...inv.backendExtra,
    ...form,
    field_sources,
    investigation_method: inv.investigationMethod,
    whys: inv.whys
      .filter((w) => filled(w.question))
      .map((w) => ({ ...w, status: filled(w.answer) ? "answered" : "unanswered" })),
    potential_root_causes: inv.potentialCauses
      .filter((c) => filled(c.hypothesis))
      .map((c) => ({ ...c, evidence_needed: cleanStrings(c.evidence_needed), status: c.status || "unverified" })),
    missing_evidence: cleanStrings(inv.missingEvidence),
    corrective_actions: actions(inv.correctiveActions, "corrective"),
    preventive_actions: actions(inv.preventiveActions, "preventive"),
    uncertainties: cleanStrings(inv.uncertainties),
    status: inv.status,
    source_type: inv.sourceType,
    is_mock: inv.isMock,
  };
}
