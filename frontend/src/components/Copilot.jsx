import { useEffect, useRef, useState } from "react";
import { useDispatch, useSelector, useStore } from "react-redux";
import { addMessage, setLoading } from "../features/chatSlice";
import { applyAnalysis, patchFields } from "../features/investigationSlice";
import { analyze, fromBackendDraft, toBackendDraft } from "../services/api";

export default function Copilot() {
  const d = useDispatch();
  const store = useStore();
  const { messages, loading } = useSelector((s) => s.chat);
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [sourceType, setSourceType] = useState("text");
  const fileRef = useRef();
  const endRef = useRef();

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const reply = (t) => d(addMessage({ role: "ai", text: t }));

  const pickFile = (e) => {
    const f = e.target.files[0];
    e.target.value = "";
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".pdf")) return reply("Only PDF files are supported. Paste the text instead, or attach a PDF.");
    if (f.size > 10 * 1024 * 1024) return reply("That PDF is larger than 10 MB. Attach a smaller file.");
    setFile(f);
  };

  const send = async () => {
    const t = text.trim();
    if (loading || (!t && !file)) return;
    const shown = file ? `Attached: ${file.name}` : t.length > 300 ? `${t.slice(0, 300)}…` : t;
    d(addMessage({ role: "user", text: shown }));
    d(setLoading(true));
    try {
      // Send the current form as context so the backend can tell a correction
      // or a question apart from a new report.
      const inv = store.getState().investigation;
      const res = await analyze({
        text: t, sourceType, file,
        currentDraft: inv.hasDraft ? toBackendDraft(inv) : null,
      });
      if (res.intent === "new_document" && res.draft) d(applyAnalysis(fromBackendDraft(res.draft)));
      else if (res.intent === "correction" && res.changed_fields) d(patchFields(res.changed_fields));
      reply(res.reply);
      setText(""); setFile(null); // cleared only after success, so a failure keeps the input
    } catch (e) {
      reply(`${e.message} Your input is still in the box, so you can try again.`);
    } finally {
      d(setLoading(false));
    }
  };

  return (
    <aside className="copilot">
      <h2>Qualivance RCA Copilot</h2>
      <p className="sub" style={{ margin: 0 }}>Paste an incident report or email, or attach a PDF.</p>
      <div className="chat-messages">
        {messages.map((m) => <div key={m.id} className={`msg ${m.role}`}>{m.text}</div>)}
        {loading && <div className="msg ai">Analyzing… this can take up to a minute.</div>}
        <div ref={endRef} />
      </div>
      {file && <div className="notice" style={{ marginBottom: 8 }}>Ready to send: {file.name}. Typed text is ignored while a PDF is attached.{" "}
        <button className="btn btn-ghost btn-small" onClick={() => setFile(null)}>Remove</button></div>}
      <div className="chat-tools">
        <label className="sub" htmlFor="srcType">Pasted text is a</label>
        <select id="srcType" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
          <option value="text">Incident report</option>
          <option value="email">Email</option>
        </select>
      </div>
      <div className="chat-input multi">
        <input ref={fileRef} type="file" accept=".pdf" hidden onChange={pickFile} />
        <button className="icon-btn" title="Attach PDF" aria-label="Attach PDF" onClick={() => fileRef.current.click()}>📎</button>
        <textarea rows={2} value={text} aria-label="Message" disabled={loading}
          placeholder="Paste a report or email, or type a correction. Enter to send, Shift+Enter for a new line."
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
        <button className="send-btn" aria-label="Send" disabled={loading} onClick={send}>➤</button>
      </div>
    </aside>
  );
}
