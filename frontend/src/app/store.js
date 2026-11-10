import { configureStore } from "@reduxjs/toolkit";
import investigation from "../features/investigationSlice";
import chat from "../features/chatSlice";
import history from "../features/historySlice";

export const store = configureStore({
  reducer: { investigation, chat, history },
});
