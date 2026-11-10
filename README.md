# Qualivance RCA

AI-assisted Root Cause Analysis for pharmaceutical API quality incidents.

Paste an incident report or email, or attach a PDF. An AI copilot extracts the facts, fills an editable RCA form, drafts a 5 Whys analysis with unverified potential causes, lists missing evidence, and proposes corrective and preventive actions (CAPA). A qualified person reviews and edits everything before saving. Nothing is approved automatically.

All sample data is fictional.

![Qualivance RCA: the AI copilot fills the RCA form from an uploaded PDF](docs/screenshot.png)

## Features

- **Three inputs:** pasted text, pasted email, or PDF (up to 10 MB).
- **AI copilot:** a chat panel fills the form and accepts corrections such as "sorry, the batch number is B-TEST-99". Only the named field changes.
- **Structured analysis:** 5 Whys, potential root causes with evidence needed, missing evidence, and draft CAPA.
- **Clear labels:** *From source*, *AI suggestion, unverified*, *Evidence needed*, *Edited by you*.
- **Persistence:** save, list, reopen and update investigations in PostgreSQL.
- **Mock mode:** fixed fictional answers with no AI calls, for rehearsal and offline tests.

## Architecture

```
React + Redux (Vite)  --HTTP/JSON-->  FastAPI
                                        |-- document_parser.py   text, email, PDF (PyMuPDF)
                                        |-- ai_workflow.py       LangGraph workflow
                                        |       classify -> extract -> validate evidence
                                        |       -> root cause -> CAPA -> validate output
                                        |       (corrections and questions take short paths)
                                        |-- llm.py               the only module that calls Groq
                                        '-- PostgreSQL           SQLAlchemy, drafts stored as JSON
```

The Groq key is read by the backend only and never reaches the browser.

## Safeguards (enforced in code)

- Extracted facts must appear in the source text, otherwise they are blanked and flagged.
- The report is treated as data, so embedded instructions such as "approve and release the batch" are ignored.
- Causes are always `unverified`. Actions are always drafts. Advice to release, approve, override or bypass is removed.
- Only three statuses exist: Draft, Ready for Review, Saved. There is no Approved status.
- Errors return a clear message and keep the user's input. A database failure never shows a false "Saved".

## Tech stack

React, Redux Toolkit, Vite | Python, FastAPI | LangGraph | Groq | PostgreSQL, SQLAlchemy | PyMuPDF

## Setup

**Prerequisites:** Python 3.10+, Node.js, PostgreSQL, and a Groq API key (https://console.groq.com/keys).

```bash
git clone https://github.com/shrutirathore25/Qualivance.git
cd Qualivance
```

**Backend**

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env          # macOS/Linux: cp .env.example .env
```

Fill in `.env` (see below), create an empty database (`CREATE DATABASE qualivance_rca;`), then:

```powershell
uvicorn main:app --reload --port 8000
```

Tables are created automatically on first use. Check http://localhost:8000/api/health.

**Frontend** (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Configuration

Set in `backend/.env`. Never commit this file.

| Variable | Description |
|---|---|
| `GROQ_API_KEY` | Your Groq key |
| `GROQ_MODEL` | Model name, for example `openai/gpt-oss-120b`. Run `python check_groq.py` to list models your key can use |
| `DATABASE_URL` | For example `postgresql+psycopg2://postgres:password@localhost:5432/qualivance_rca` |
| `AI_MODE` | Optional. `mock` for fixed fictional answers, no Groq calls |

## Try it

Paste this fictional report into the copilot:

> During review of fictional batch B-DEMO-014, the moisture result was recorded as 1.2%; the fictional specification states a maximum of 0.5%. The report does not include dryer logs, calibration records, or the full laboratory method.

Batch, result and specification are filled from the source. Product and date stay blank. Causes appear as unverified with the evidence needed.

## Tests

From `backend/` with the virtual environment active:

```powershell
python run_checks.py      # offline: schemas and parsing
python try_live.py        # live tests against the real model
```

API checks without model calls: start the backend with `$env:AI_MODE="mock"`, then run `python check_api.py` in a second terminal. Groq applies rate limits, so leave about 20 seconds between real analyses.
