import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { listInvestigations } from "../services/api";

// The list now comes from the database (GET /api/investigations).
export const fetchInvestigations = createAsyncThunk(
  "history/fetch",
  async (_, { rejectWithValue }) => {
    try { return await listInvestigations(); }
    catch (e) { return rejectWithValue(e.message); }
  }
);

const slice = createSlice({
  name: "history",
  initialState: { items: [], currentId: null, loading: false, error: null },
  reducers: {
    setCurrent(s, { payload }) { s.currentId = payload; },
    setHistoryError(s, { payload }) { s.error = payload; },
  },
  extraReducers: (b) => {
    b.addCase(fetchInvestigations.pending, (s) => { s.loading = true; s.error = null; })
      .addCase(fetchInvestigations.fulfilled, (s, { payload }) => { s.loading = false; s.items = payload; })
      .addCase(fetchInvestigations.rejected, (s, { payload }) => {
        s.loading = false;
        s.error = payload || "Could not load investigations.";
      });
  },
});
export const { setCurrent, setHistoryError } = slice.actions;
export default slice.reducer;
