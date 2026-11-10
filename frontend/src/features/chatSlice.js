import { createSlice } from "@reduxjs/toolkit";

const initialState = {
  messages: [
    {
      id: 1,
      role: "ai",
      text: "Ready to investigate. Paste an incident report or email, or attach a PDF. I will extract the facts and fill in the form.",
    },
  ],
  loading: false,
};

const slice = createSlice({
  name: "chat",
  initialState,
  reducers: {
    addMessage(state, { payload }) {
      state.messages.push({ id: Date.now() + Math.random(), ...payload });
    },
    setLoading(state, { payload }) {
      state.loading = payload;
    },
    resetChat: () => initialState,
  },
});

export const { addMessage, setLoading, resetChat } = slice.actions;
export default slice.reducer;
