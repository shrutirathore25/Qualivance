import { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { resetInvestigation } from "./features/investigationSlice";
import { resetChat } from "./features/chatSlice";
import { setCurrent, setHistoryError } from "./features/historySlice";
import { openInvestigation } from "./features/thunks";
import Dashboard from "./components/Dashboard";
import RcaForm from "./components/RcaForm";
import Copilot from "./components/Copilot";

const BADGE = { Draft: "status-draft", "Ready for Review": "status-ready", Saved: "status-saved" };

export default function App() {
  const [view, setView] = useState("dashboard");
  const d = useDispatch();
  const status = useSelector((s) => s.investigation.status);

  const startNew = () => {
    d(resetInvestigation()); d(resetChat()); d(setCurrent(null)); d(setHistoryError(null));
    setView("investigation");
  };
  const open = async (rec) => {
    d(resetChat());
    const ok = await d(openInvestigation(rec.id));
    if (ok) setView("investigation");
  };
  const nav = (id, label, fn) => (
    <button className={`nav-link ${view === id ? "active" : ""}`} onClick={fn || (() => setView(id))}>{label}</button>
  );

  return (
    <>
      <nav className="nav"><div className="nav-pill">
        {nav("dashboard", "Dashboard")}
        {nav("investigation", "New investigation", startNew)}
        {nav("history", "History")}
      </div></nav>

      {view === "investigation" ? (
        <div className="page">
          <div className="page-head">
            <div><h1>Qualivance RCA</h1><p className="sub">Pharmaceutical API quality module</p></div>
            <span className={`status-badge ${BADGE[status] || "status-draft"}`}>{status}</span>
          </div>
          <div className="layout"><RcaForm /><Copilot /></div>
        </div>
      ) : (
        <Dashboard onNew={startNew} onOpen={open} showAll={view === "history"} />
      )}
    </>
  );
}

