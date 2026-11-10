// Actions that talk to the backend and then update Redux.
import { createInvestigation, getInvestigation, updateInvestigation, fromBackendDraft, toBackendDraft } from "../services/api";
import { applyAnalysis, markSaved, setSaveState } from "./investigationSlice";
import { fetchInvestigations, setCurrent, setHistoryError } from "./historySlice";

// Save draft: creates a record the first time, updates it afterwards.
// "Saved" is shown ONLY after the backend confirms. A failure never looks like success.
export const saveCurrent = () => async (dispatch, getState) => {
  const { investigation, history } = getState();
  if (investigation.saveState === "saving") return;
  dispatch(setSaveState({ state: "saving" }));
  try {
    const draft = toBackendDraft(investigation);
    const rec = history.currentId
      ? await updateInvestigation(history.currentId, draft)
      : await createInvestigation(draft);
    dispatch(setCurrent(rec.id));
    dispatch(markSaved({ at: rec.updated_at }));
    dispatch(fetchInvestigations());
  } catch (e) {
    dispatch(setSaveState({ state: "error", message: e.message }));
  }
};

// Open a saved record from the database. Returns true on success.
export const openInvestigation = (id) => async (dispatch) => {
  try {
    const rec = await getInvestigation(id);
    dispatch(applyAnalysis({ ...fromBackendDraft(rec.draft), status: rec.status }));
    dispatch(setCurrent(rec.id));
    dispatch(markSaved({ at: rec.updated_at }));
    return true;
  } catch (e) {
    dispatch(setHistoryError(e.message));
    return false;
  }
};
