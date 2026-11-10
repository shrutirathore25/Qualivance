"""Repeatable API test. Start the backend first (see PHASE5B_README.txt), then:
    python check_api.py
Uses only the Python standard library. Uses fictional data only."""
import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://localhost:8000"
results = []


def call(method, path, data=None, form=None):
    body, headers = None, {}
    if data is not None:
        body, headers = json.dumps(data).encode(), {"Content-Type": "application/json"}
    if form is not None:
        body = urllib.parse.urlencode(form).encode()
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def check(name, ok, info=""):
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{info}]" if info and not ok else ""))


REPORT = ("During review of fictional batch B-DEMO-014, the moisture result was recorded "
          "as 1.2%; the fictional specification states a maximum of 0.5%. The report does "
          "not include dryer logs, calibration records, or the full laboratory method.")

s, h = call("GET", "/api/health")
check("Health endpoint ok and database reachable", s == 200 and h.get("status") == "ok" and h.get("database") == "ok", h)

s, a = call("POST", "/api/analyze", form={"text": REPORT, "source_type": "text"})
check("Analyze pasted text returns a draft", s == 200 and a.get("draft") is not None, (s, a))
draft = a.get("draft") or {}
check("Batch number extracted", draft.get("batch_number") == "B-DEMO-014", draft.get("batch_number"))

s, c = call("POST", "/api/analyze", form={"text": "sorry the batch number is B-TEST-99",
                                          "source_type": "text",
                                          "current_draft": json.dumps(draft)})
check("Chat correction changes the batch number", s == 200 and (c.get("changed_fields") or {}).get("batch_number") == "B-TEST-99", (s, c))

s, e = call("POST", "/api/analyze", form={"text": "   ", "source_type": "text"})
check("Empty input gives a clear 422 message", s == 422 and e.get("code") and e.get("message"), (s, e))

s, sv = call("POST", "/api/investigations", data={"draft": draft, "source_text": REPORT})
check("Save creates a record with status Saved", s == 201 and sv.get("status") == "Saved" and sv.get("id"), (s, sv))
rid = sv.get("id")

edited = dict(sv.get("draft") or {})
edited["batch_number"] = "B-EDITED-77"
s, up = call("PUT", f"/api/investigations/{rid}", data={"draft": edited})
check("Update stores the user-edited value", s == 200 and up.get("batch_number") == "B-EDITED-77", (s, up))

s, g = call("GET", f"/api/investigations/{rid}")
check("Reopen returns the edited value", s == 200 and g["draft"].get("batch_number") == "B-EDITED-77", (s, g))

s, lst = call("GET", "/api/investigations")
check("List contains the saved record, newest first", s == 200 and isinstance(lst, list) and lst and lst[0]["id"] == rid, (s, lst))

s, nf = call("GET", "/api/investigations/999999")
check("Missing record gives 404 with a message", s == 404 and nf.get("message"), (s, nf))

bad = dict(edited); bad["status"] = "Approved"
s, ap = call("POST", "/api/investigations", data={"draft": bad})
check("Status 'Approved' is rejected", s == 422, (s, ap))

print(f"\n{sum(results)}/{len(results)} checks passed")
