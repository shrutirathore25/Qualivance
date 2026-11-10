"""FastAPI app: health, analyze (AI), and save/list/open/update investigations."""
import logging
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # must run before ai_workflow / llm read the environment

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

import database
from database import DatabaseUnavailable, get_db
from document_parser import DocumentParseError, parse_email, parse_pdf, parse_text
from ai_workflow import run_workflow
from llm import LLMError
from models import Investigation
from schemas import InvestigationDraft

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")

MAX_PDF_BYTES = 10 * 1024 * 1024
MAX_SOURCE_TEXT = 100_000

app = FastAPI(title="Qualivance RCA API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code, self.code, self.message = status_code, code, message


def _err(status: int, code: str, message: str):
    return JSONResponse(status_code=status, content={"code": code, "message": message})


@app.exception_handler(ApiError)
def _api_error(request: Request, exc: ApiError):
    return _err(exc.status_code, exc.code, exc.message)


@app.exception_handler(DocumentParseError)
def _parse_error(request: Request, exc: DocumentParseError):
    return _err(422, exc.code, exc.message)


@app.exception_handler(LLMError)
def _llm_error(request: Request, exc: LLMError):
    return _err(exc.http_status, exc.code, exc.message)


@app.exception_handler(DatabaseUnavailable)
def _db_unavailable(request: Request, exc: DatabaseUnavailable):
    return _err(503, "database_unavailable", str(exc))


@app.exception_handler(SQLAlchemyError)
def _db_error(request: Request, exc: SQLAlchemyError):
    log.error("database error: %s", type(exc).__name__)  # no details, no secrets
    return _err(503, "database_error",
                "The database is not available right now. Nothing was saved. "
                "Check that PostgreSQL is running and try again.")


@app.exception_handler(Exception)
def _unexpected(request: Request, exc: Exception):
    log.error("unexpected error: %s", type(exc).__name__)
    return _err(500, "server_error", "Something went wrong on the server. Please try again.")


# ---------------------------------------------------------------- health
@app.get("/api/health")
def health():
    db_state = "not_configured"
    if database.engine is not None:
        try:
            with database.engine.connect() as conn:
                conn.execute(sql_text("SELECT 1"))
            db_state = "ok"
        except Exception:
            db_state = "unavailable"
    return {"status": "ok", "database": db_state}


# --------------------------------------------------------------- analyze
@app.post("/api/analyze")
def analyze(
    text: Optional[str] = Form(None),
    source_type: Optional[str] = Form(None),
    current_draft: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    # plain `def` -> FastAPI runs it in a thread pool, so the slow AI call
    # does not block other requests.
    if file is not None and file.filename:
        data = file.file.read(MAX_PDF_BYTES + 1)  # parser rejects > 10 MB
        parsed = parse_pdf(data, file.filename)
    elif source_type == "email":
        parsed = parse_email(text or "")
    else:
        parsed = parse_text(text or "")

    draft_obj = None
    if current_draft:
        try:
            draft_obj = InvestigationDraft.model_validate_json(current_draft)
        except ValidationError:
            raise ApiError(422, "invalid_draft",
                           "The current form data is not valid. Reload the page and try again.")

    return run_workflow(parsed.text, parsed.source_type, draft_obj)


# ------------------------------------------------------- investigations
def _validated_draft(raw) -> InvestigationDraft:
    try:
        draft = InvestigationDraft.model_validate(raw)
    except ValidationError:
        raise ApiError(422, "invalid_draft", "The investigation data is not valid, so it was not saved.")
    # Saving is the user's explicit action. 'Approved' does not exist.
    return draft.model_copy(update={"status": "Saved"})


def _full(rec: Investigation) -> dict:
    return {
        "id": rec.id,
        "batch_number": rec.batch_number,
        "status": rec.status,
        "source_type": rec.source_type,
        "draft": rec.draft,
        "source_text": rec.source_text,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


def _summary(rec: Investigation) -> dict:
    d = rec.draft or {}
    return {
        "id": rec.id,
        "batch_number": rec.batch_number,
        "product_name": d.get("product_name"),
        "status": rec.status,
        "source_type": rec.source_type,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


@app.post("/api/investigations", status_code=201)
def create_investigation(body: dict, db: Session = Depends(get_db)):
    draft = _validated_draft(body.get("draft"))
    src = body.get("source_text")
    rec = Investigation(
        batch_number=draft.batch_number,
        status="Saved",
        source_type=draft.source_type,
        draft=draft.model_dump(mode="json"),
        source_text=src[:MAX_SOURCE_TEXT] if isinstance(src, str) and src.strip() else None,
    )
    db.add(rec)
    db.commit()
    return _full(rec)


@app.get("/api/investigations")
def list_investigations(db: Session = Depends(get_db)):
    rows = db.scalars(select(Investigation).order_by(Investigation.updated_at.desc())).all()
    return [_summary(r) for r in rows]


@app.get("/api/investigations/{inv_id}")
def get_investigation(inv_id: int, db: Session = Depends(get_db)):
    rec = db.get(Investigation, inv_id)
    if rec is None:
        raise ApiError(404, "not_found", f"Investigation {inv_id} was not found.")
    return _full(rec)


@app.put("/api/investigations/{inv_id}")
def update_investigation(inv_id: int, body: dict, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    rec = db.get(Investigation, inv_id)
    if rec is None:
        raise ApiError(404, "not_found", f"Investigation {inv_id} was not found.")
    draft = _validated_draft(body.get("draft"))
    rec.batch_number = draft.batch_number
    rec.status = "Saved"
    rec.source_type = draft.source_type
    rec.draft = draft.model_dump(mode="json")
    rec.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _full(rec)
