"""
document_parser.py - turns pasted text, pasted emails and PDFs into clean text.

Safety rules:
  * Uploaded content is only ever READ as data. It is never executed or evaluated.
  * Size and type are checked before anything is processed.
  * Whitespace is tidied; words are never changed.
  * Scanned (image-only) PDFs get a clear message because OCR is not configured.
"""
import re
from typing import Optional

import pymupdf  # PyMuPDF

from schemas import ParsedDocument

MAX_PDF_BYTES = 10 * 1024 * 1024   # 10 MB
MAX_PDF_PAGES = 50
MAX_TEXT_CHARS = 100_000
MIN_PDF_TEXT_CHARS = 40            # below this, treat the PDF as scanned/empty


class DocumentParseError(Exception):
    """Raised with a message that is safe to show directly to the user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def normalise_whitespace(text: str) -> str:
    """Tidy spacing only. Never alters words, numbers or punctuation."""
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)          # collapse runs of spaces/tabs
    text = re.sub(r" *\n *", "\n", text)               # trim around line breaks
    text = re.sub(r"\n{3,}", "\n\n", text)             # at most one blank line
    return text.strip()


def _check_text(text: Optional[str]) -> str:
    if text is None or not text.strip():
        raise DocumentParseError("empty_input", "The input is empty. Paste an incident report or email, or attach a PDF.")
    if len(text) > MAX_TEXT_CHARS:
        raise DocumentParseError(
            "too_long", f"The text is too long ({len(text):,} characters). The limit is {MAX_TEXT_CHARS:,}."
        )
    return normalise_whitespace(text)


def parse_text(text: Optional[str]) -> ParsedDocument:
    clean = _check_text(text)
    return ParsedDocument(text=clean, source_type="text", char_count=len(clean))


_HEADER = re.compile(r"^(from|to|cc|bcc|subject|date|sent)\s*:\s*(.*)$", re.IGNORECASE)


def parse_email(raw: Optional[str]) -> ParsedDocument:
    """Accepts a pasted email, with or without headers. Headers are kept as text
    (they can contain the date or sender) and the subject is also surfaced."""
    clean = _check_text(raw)
    subject = None
    for line in clean.split("\n")[:15]:           # headers appear at the top
        m = _HEADER.match(line.strip())
        if m and m.group(1).lower() == "subject":
            subject = m.group(2).strip() or None
            break
    warnings = []
    if subject is None:
        warnings.append("No 'Subject:' line found; treating the whole paste as the email body.")
    return ParsedDocument(
        text=clean, source_type="email", char_count=len(clean),
        email_subject=subject, warnings=warnings,
    )


def parse_pdf(data: bytes, filename: str = "upload.pdf") -> ParsedDocument:
    """Extract text from a text-based PDF."""
    if not data:
        raise DocumentParseError("empty_file", "The uploaded file is empty.")
    if len(data) > MAX_PDF_BYTES:
        raise DocumentParseError("file_too_large", f"The PDF is larger than {MAX_PDF_BYTES // (1024 * 1024)} MB.")
    if not filename.lower().endswith(".pdf") or not data.lstrip()[:5] == b"%PDF-":
        raise DocumentParseError("not_a_pdf", "This file is not a valid PDF. Please upload a .pdf file.")

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise DocumentParseError("malformed_pdf", "The PDF could not be opened. It may be damaged. Try another copy or paste the text.")

    try:
        if doc.needs_pass:
            raise DocumentParseError("encrypted_pdf", "The PDF is password-protected. Remove the password or paste the text instead.")
        if doc.page_count == 0:
            raise DocumentParseError("empty_pdf", "The PDF has no pages.")

        warnings = []
        pages_to_read = min(doc.page_count, MAX_PDF_PAGES)
        if doc.page_count > MAX_PDF_PAGES:
            warnings.append(f"Only the first {MAX_PDF_PAGES} of {doc.page_count} pages were read.")

        chunks = []
        try:
            for i in range(pages_to_read):
                chunks.append(doc[i].get_text("text"))
        except Exception:
            raise DocumentParseError("malformed_pdf", "The PDF text could not be read. It may be damaged. Try another copy or paste the text.")

        text = normalise_whitespace("\n\n".join(chunks))
        if len(text.replace("\n", "").replace(" ", "")) < MIN_PDF_TEXT_CHARS:
            raise DocumentParseError(
                "scanned_pdf",
                "No readable text was found. This looks like a scanned or image-only PDF, and OCR is not configured. "
                "Paste the text instead, or upload a text-based PDF.",
            )
        if len(text) > MAX_TEXT_CHARS:
            text = text[:MAX_TEXT_CHARS]
            warnings.append(f"The document was long; only the first {MAX_TEXT_CHARS:,} characters are used.")
        return ParsedDocument(
            text=text, source_type="pdf", char_count=len(text),
            page_count=doc.page_count, warnings=warnings,
        )
    finally:
        doc.close()
