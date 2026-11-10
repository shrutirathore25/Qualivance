import { useEffect } from "react";
import { useDispatch, useSelector } from "react-redux";
import { fetchInvestigations } from "../features/historySlice";

const SRC = { pdf: "PDF", text: "Pasted text", email: "Email" };

export default function Dashboard({ onNew, onOpen, showAll }) {
  const d = useDispatch();
  const { items, loading, error } = useSelector((s) => s.history);
  useEffect(() => { d(fetchInvestigations()); }, [d]);
  const rows = showAll ? items : items.slice(0, 5);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>{showAll ? "Investigation history" : "Root cause investigations"}</h1>
          <p className="sub">Draft, review and save quality investigations with AI assistance.</p>
        </div>
        <button className="btn btn-primary" onClick={onNew}>New investigation</button>
      </div>
      {!showAll && (
        <div className="stats">
          <div className="stat"><b>{items.length}</b><span>Investigations</span></div>
          <div className="stat"><b>{items.filter((i) => i.status === "Saved").length}</b><span>Saved drafts</span></div>
          <div className="stat"><b>0</b><span>Approved</span></div>
        </div>
      )}
      <div className="card">
        <h2>{showAll ? "All investigations" : "Recent investigations"}</h2>
        {error && <div className="notice">{error} <button className="btn btn-ghost btn-small" onClick={() => d(fetchInvestigations())}>Retry</button></div>}
        {loading && <p className="empty">Loading…</p>}
        {!loading && !error && rows.length === 0 && <p className="empty">No investigations yet. Start one and save it as a draft.</p>}
        {rows.map((r) => (
          <div key={r.id} className="hist-row">
            <div>
              <b>{r.batch_number || r.product_name || `Untitled investigation #${r.id}`}</b>
              <div className="sub">
                {r.status}{r.source_type ? ` · ${SRC[r.source_type] || r.source_type}` : ""} · Saved {new Date(r.updated_at).toLocaleString()}
              </div>
            </div>
            <button className="btn btn-ghost btn-small" onClick={() => onOpen(r)}>Open</button>
          </div>
        ))}
        <p className="sub" style={{ marginTop: 12 }}>Saved investigations are stored in the PostgreSQL database and survive a page refresh.</p>
      </div>
    </div>
  );
}
