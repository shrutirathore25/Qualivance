import { useDispatch, useSelector } from "react-redux";
import { updateField, updateListItem, addListItem, removeListItem } from "../features/investigationSlice";
import { saveCurrent } from "../features/thunks";

// [key, label, kind]  kind: undefined = one line, "area" = text box, "select" = classification
const FIELDS = [
  ["deviation_id", "Deviation ID"], ["classification", "Classification", "select"],
  ["product_name", "Product / API"], ["batch_number", "Batch number"],
  ["incident_date", "Incident date"], ["area_equipment", "Area / equipment"],
  ["observed_result", "Observed result"], ["specification", "Specification"],
  ["deviation_description", "Deviation description", "area"],
  ["immediate_containment", "Immediate containment", "area"],
  ["impact_assessment", "Impact assessment", "area"],
  ["immediate_action", "Immediate action", "area"],
  ["effectiveness_check", "Effectiveness check", "area"],
];
const SRC = { source: ["From source", "tag-source"], user: ["Edited by you", "tag-user"] };
const SOURCE_LABEL = { pdf: "PDF", text: "Pasted text", email: "Email" };
const CAPA_FIELDS = [["description", "Action"], ["rationale", "Rationale"], ["linked_cause", "Linked cause"], ["verification", "How to verify"]];

const Tag = ({ cls, children }) => <span className={`tag ${cls}`}>{children}</span>;

function Area({ label, value, onChange }) {
  return (
    <div className="field full" style={{ marginBottom: 10 }}>
      <label>{label}</label>
      <textarea rows={2} value={value} onChange={onChange} />
    </div>
  );
}

function ObjectList({ title, tag, tagCls, itemCls, list, fields, blank, addLabel, empty }) {
  const d = useDispatch();
  const items = useSelector((s) => s.investigation[list]);
  return (
    <section className="card">
      <div className="card-head"><h2>{title}</h2><Tag cls={tagCls}>{tag}</Tag></div>
      {items.length === 0 && <p className="empty">{empty}</p>}
      {items.map((it, i) => (
        <div key={i} className={`item ${itemCls}`}>
          <div className="item-top">
            <Tag cls={tagCls}>{tag}</Tag>
            <button className="btn btn-ghost btn-small" onClick={() => d(removeListItem({ list, index: i }))}>Remove</button>
          </div>
          {fields.map(([key, label, lines]) => (
            <Area key={key} label={label}
              value={lines ? (it[key] || []).join("\n") : it[key] || ""}
              onChange={(e) => d(updateListItem({ list, index: i, key, value: lines ? e.target.value.split("\n") : e.target.value }))} />
          ))}
        </div>
      ))}
      <button className="btn btn-ghost btn-small" onClick={() => d(addListItem({ list, item: blank }))}>{addLabel}</button>
    </section>
  );
}

function StringList({ title, tag, tagCls, list, empty, addLabel }) {
  const d = useDispatch();
  const items = useSelector((s) => s.investigation[list]);
  return (
    <section className="card">
      <div className="card-head"><h2>{title}</h2><Tag cls={tagCls}>{tag}</Tag></div>
      {items.length === 0 && <p className="empty">{empty}</p>}
      {items.map((t, i) => (
        <div key={i} className="chat-input" style={{ background: "var(--beige)", marginBottom: 8 }}>
          <input value={t} aria-label={title} onChange={(e) => d(updateListItem({ list, index: i, key: null, value: e.target.value }))} />
          <button className="btn btn-ghost btn-small" onClick={() => d(removeListItem({ list, index: i }))}>Remove</button>
        </div>
      ))}
      <button className="btn btn-ghost btn-small" onClick={() => d(addListItem({ list, item: "" }))}>{addLabel}</button>
    </section>
  );
}

export default function RcaForm() {
  const d = useDispatch();
  const inv = useSelector((s) => s.investigation);
  const { form, fieldSources, saveState, saveMessage, dirty, savedAt } = inv;
  const blankCause = { hypothesis: "", rationale: "", evidence_needed: [], status: "unverified" };
  const blankAction = (type) => ({ type, description: "", rationale: "", linked_cause: "", verification: "", status: "draft" });

  let saveText = "AI output is a suggestion until a qualified person confirms it.";
  if (saveState === "saving") saveText = "Saving…";
  else if (saveState === "error") saveText = `Save failed. Nothing was saved. ${saveMessage}`;
  else if (dirty) saveText = "You have unsaved changes.";
  else if (saveState === "saved" && savedAt) saveText = `Saved to the database at ${new Date(savedAt).toLocaleTimeString()}.`;

  return (
    <div>
      {inv.isMock && <div className="notice">Demo mode: the content below comes from fixed fictional sample answers, not the real AI.</div>}
      <section className="card">
        <div className="card-head"><h2>Incident facts</h2>{inv.sourceType && <Tag cls="tag-source">{SOURCE_LABEL[inv.sourceType] || inv.sourceType}</Tag>}</div>
        <div className="field-grid">
          {FIELDS.map(([key, label, kind]) => {
            const t = SRC[fieldSources[key]];
            const onChange = (e) => d(updateField({ field: key, value: e.target.value }));
            return (
              <div key={key} className={`field ${kind === "area" ? "full" : ""}`}>
                <label>{label}{t && <Tag cls={t[1]}>{t[0]}</Tag>}</label>
                {kind === "area" ? <textarea rows={2} value={form[key]} placeholder="Awaiting AI extraction…" onChange={onChange} />
                  : kind === "select" ? (
                    <select value={form[key]} onChange={onChange}>
                      <option value="">Not stated</option>
                      <option value="minor">Minor</option>
                      <option value="major">Major</option>
                      <option value="critical">Critical</option>
                    </select>
                  ) : <input value={form[key]} placeholder="Awaiting AI extraction…" onChange={onChange} />}
              </div>
            );
          })}
        </div>
      </section>

      <ObjectList title="5 Whys" tag="AI suggestion, unverified" tagCls="tag-ai" itemCls="item-ai" list="whys"
        fields={[["question", "Why?"], ["answer", "Answer (blank if not supported by evidence)"]]}
        blank={{ question: "", answer: "", status: "unanswered" }} addLabel="Add a why" empty="No whys yet. Analyze a report to get suggestions." />
      <ObjectList title="Potential root causes" tag="AI suggestion, unverified" tagCls="tag-ai" itemCls="item-ai" list="potentialCauses"
        fields={[["hypothesis", "Hypothesis"], ["rationale", "Rationale"], ["evidence_needed", "Evidence needed (one per line)", true]]}
        blank={blankCause} addLabel="Add a cause" empty="No causes suggested yet." />
      <StringList title="Missing evidence" tag="Evidence needed" tagCls="tag-evidence" list="missingEvidence" addLabel="Add item" empty="Nothing flagged yet." />
      <ObjectList title="Corrective actions" tag="Draft, needs review" tagCls="tag-ai" itemCls="item-ai" list="correctiveActions"
        fields={CAPA_FIELDS} blank={blankAction("corrective")} addLabel="Add corrective action" empty="No corrective actions yet." />
      <ObjectList title="Preventive actions" tag="Draft, needs review" tagCls="tag-ai" itemCls="item-ai" list="preventiveActions"
        fields={CAPA_FIELDS} blank={blankAction("preventive")} addLabel="Add preventive action" empty="No preventive actions yet." />
      <StringList title="Uncertainties" tag="Needs your judgment" tagCls="tag-evidence" list="uncertainties" addLabel="Add item" empty="Nothing flagged yet." />

      <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
        <button className="btn btn-primary" disabled={saveState === "saving"} onClick={() => d(saveCurrent())}>
          {saveState === "saving" ? "Saving…" : "Save draft"}
        </button>
        <span className="sub" role="status" style={saveState === "error" ? { color: "#B3261E", fontWeight: 600 } : undefined}>{saveText}</span>
      </div>
    </div>
  );
}
