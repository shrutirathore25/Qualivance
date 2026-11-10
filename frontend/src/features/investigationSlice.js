import { createSlice } from "@reduxjs/toolkit";

// One list for the whole app. Names match the backend draft fields exactly.
export const FORM_FIELDS = [
  "deviation_id", "classification", "product_name", "batch_number",
  "incident_date", "area_equipment", "observed_result", "specification",
  "deviation_description", "immediate_containment", "impact_assessment",
  "immediate_action", "effectiveness_check",
];

const emptyForm = Object.fromEntries(FORM_FIELDS.map((f) => [f, ""]));

const initialState = {
  form: { ...emptyForm },
  fieldSources: {},
  investigationMethod: "5_whys",
  whys: [],
  potentialCauses: [],
  missingEvidence: [],
  correctiveActions: [],
  preventiveActions: [],
  uncertainties: [],
  status: "Draft",
  sourceType: null,
  isMock: false,
  hasDraft: false,     // true once an analysis (or a saved record) is loaded
  backendExtra: {},    // backend fields the form does not show (kept so nothing is lost)
  dirty: false,        // edits not saved yet
  saveState: "idle",   // idle | saving | saved | error
  saveMessage: "",
  savedAt: null,
};

// Any edit after saving means the saved copy is out of date.
const touch = (state) => {
  state.dirty = true;
  if (state.status === "Saved") state.status = "Draft";
};

const slice = createSlice({
  name: "investigation",
  initialState,
  reducers: {
    updateField(state, { payload: { field, value } }) {
      state.form[field] = value;
      state.fieldSources[field] = "user";
      touch(state);
    },
    patchFields(state, { payload }) {
      Object.entries(payload).forEach(([field, value]) => {
        if (FORM_FIELDS.includes(field)) {
          state.form[field] = value ?? "";
          state.fieldSources[field] = "user";
        }
      });
      touch(state);
    },
    // Used for a fresh AI analysis and for loading a saved record.
    applyAnalysis(state, { payload }) {
      FORM_FIELDS.forEach((f) => {
        const v = payload.form?.[f] ?? "";
        state.form[f] = v;
        state.fieldSources[f] = payload.fieldSources?.[f] ?? (v ? "source" : "empty");
      });
      state.investigationMethod = payload.investigationMethod ?? "5_whys";
      state.whys = payload.whys ?? [];
      state.potentialCauses = payload.potentialCauses ?? [];
      state.missingEvidence = payload.missingEvidence ?? [];
      state.correctiveActions = payload.correctiveActions ?? [];
      state.preventiveActions = payload.preventiveActions ?? [];
      state.uncertainties = payload.uncertainties ?? [];
      state.sourceType = payload.sourceType ?? null;
      state.isMock = !!payload.isMock;
      state.backendExtra = payload.extra ?? {};
      state.status = payload.status ?? "Ready for Review";
      state.hasDraft = true;
      state.dirty = false;
      state.saveState = "idle";
      state.saveMessage = "";
    },
    updateListItem(state, { payload: { list, index, key, value } }) {
      if (key === null || key === undefined) state[list][index] = value;
      else state[list][index][key] = value;
      touch(state);
    },
    addListItem(state, { payload: { list, item } }) {
      state[list].push(item);
      touch(state);
    },
    removeListItem(state, { payload: { list, index } }) {
      state[list].splice(index, 1);
      touch(state);
    },
    setSaveState(state, { payload: { state: s, message } }) {
      state.saveState = s;
      state.saveMessage = message || "";
    },
    markSaved(state, { payload }) {
      state.status = "Saved";
      state.dirty = false;
      state.saveState = "saved";
      state.saveMessage = "";
      state.savedAt = payload?.at ?? new Date().toISOString();
    },
    resetInvestigation: () => initialState,
  },
});

export const {
  updateField, patchFields, applyAnalysis, updateListItem, addListItem,
  removeListItem, setSaveState, markSaved, resetInvestigation,
} = slice.actions;
export default slice.reducer;
