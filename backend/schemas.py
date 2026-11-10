"""
schemas.py - the data contract between the frontend, the AI and the database.

Every shape the app passes around is defined here once, with strict validation.
Rules baked in:
  * Missing information is None (single values) or [] (lists). Never invented.
  * AI-generated causes and actions are always "unverified" / "draft".
  * There is no "Approved" status. AI output is never auto-approved.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["pdf", "text", "email"]
Status = Literal["Draft", "Ready for Review", "Saved"]
Method = Literal["5_whys", "fishbone"]
Classification = Literal["minor", "major", "critical"]
FactConfidence = Literal["source_supported", "unclear"]
FIELD_SOURCES = Literal["source", "user", ""]


class _Base(BaseModel):
    # Ignore unknown keys from the model/UI instead of crashing; strip stray spaces.
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _blank_to_none(v):
    """Treat empty or whitespace-only strings as 'not provided'."""
    if isinstance(v, str) and not v.strip():
        return None
    return v


# ---------------------------------------------------------------- source facts
class SourceFact(_Base):
    """One fact the AI found in the source, with the quote that supports it."""
    field: str
    value: Optional[str] = None
    source_quote: Optional[str] = None
    confidence: FactConfidence = "source_supported"

    _clean = field_validator("value", "source_quote", mode="before")(_blank_to_none)


# ----------------------------------------------------------------- RCA content
class WhyStep(_Base):
    """One step of a 5 Whys chain. An unanswered step stays unanswered."""
    question: str
    answer: Optional[str] = None
    status: Literal["answered", "unanswered"] = "unanswered"

    _clean = field_validator("answer", mode="before")(_blank_to_none)


class PotentialRootCause(_Base):
    """A hypothesis. Plausible is not confirmed, so status is always 'unverified'
    until a qualified person changes it."""
    hypothesis: str
    rationale: Optional[str] = None
    evidence_needed: list[str] = Field(default_factory=list)
    status: Literal["unverified", "confirmed_by_user", "rejected_by_user"] = "unverified"


class ContributingFactor(_Base):
    factor: str
    category: Optional[str] = None  # optional fishbone category, e.g. Machine, Method
    rationale: Optional[str] = None


class Action(_Base):
    """A CAPA item. Always a draft recommendation requiring human review."""
    type: Literal["corrective", "preventive"]
    description: str
    rationale: Optional[str] = None
    linked_cause: Optional[str] = None
    verification: Optional[str] = None  # how effectiveness would be verified
    status: Literal["draft", "accepted_by_user", "rejected_by_user"] = "draft"


# ------------------------------------------------------------ the full draft
class InvestigationDraft(_Base):
    """Everything the RCA form holds. This is what the AI returns, what the user
    edits, and what is saved."""
    # incident facts
    product_name: Optional[str] = None
    batch_number: Optional[str] = None
    incident_date: Optional[str] = None
    deviation_description: Optional[str] = None
    observed_result: Optional[str] = None
    specification: Optional[str] = None
    immediate_containment: Optional[str] = None
    # deviation-record fields
    deviation_id: Optional[str] = None
    classification: Optional[Classification] = None
    area_equipment: Optional[str] = None
    impact_assessment: Optional[str] = None
    immediate_action: Optional[str] = None
    effectiveness_check: Optional[str] = None
    # investigation
    investigation_method: Method = "5_whys"
    whys: list[WhyStep] = Field(default_factory=list)
    potential_root_causes: list[PotentialRootCause] = Field(default_factory=list)
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    corrective_actions: list[Action] = Field(default_factory=list)
    preventive_actions: list[Action] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)
    source_facts: list[SourceFact] = Field(default_factory=list)
    # bookkeeping
    status: Status = "Draft"
    source_type: Optional[SourceType] = None
    field_sources: dict[str, FIELD_SOURCES] = Field(default_factory=dict)
    is_mock: bool = False

    _clean = field_validator(
        "product_name", "batch_number", "incident_date", "deviation_description",
        "observed_result", "specification", "immediate_containment", "deviation_id",
        "area_equipment", "impact_assessment", "immediate_action",
        "effectiveness_check", mode="before",
    )(_blank_to_none)

    @field_validator("classification", mode="before")
    @classmethod
    def _norm_class(cls, v):
        v = _blank_to_none(v)
        return v.lower() if isinstance(v, str) else v

    @field_validator("corrective_actions")
    @classmethod
    def _all_corrective(cls, v):
        for a in v:
            if a.type != "corrective":
                raise ValueError("corrective_actions may only hold type 'corrective'")
        return v

    @field_validator("preventive_actions")
    @classmethod
    def _all_preventive(cls, v):
        for a in v:
            if a.type != "preventive":
                raise ValueError("preventive_actions may only hold type 'preventive'")
        return v


# ------------------------------------------------------------ requests / responses
class ParsedDocument(_Base):
    """Output of document_parser.py: clean text ready for the AI."""
    text: str
    source_type: SourceType
    char_count: int
    page_count: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)
    email_subject: Optional[str] = None


class AnalyzeRequest(_Base):
    """Used by POST /api/analyze for text, email and chat messages."""
    text: str = Field(min_length=1, max_length=100_000)
    source_type: SourceType = "text"
    # Present when the user is chatting after an analysis (corrections, questions).
    current_draft: Optional[InvestigationDraft] = None


class AnalyzeResponse(_Base):
    intent: Literal["new_document", "correction", "question"] = "new_document"
    reply: str  # short message shown in the Copilot chat
    draft: Optional[InvestigationDraft] = None  # full draft for a new document
    changed_fields: dict[str, Optional[str]] = Field(default_factory=dict)  # for corrections


class SaveRequest(_Base):
    """POST /api/investigations - saves the user-edited draft, not the raw AI output."""
    draft: InvestigationDraft
    source_text: Optional[str] = None


class UpdateRequest(_Base):
    """PUT /api/investigations/{id}"""
    draft: InvestigationDraft


class InvestigationRecord(_Base):
    """What the API returns for a saved investigation."""
    id: int
    draft: InvestigationDraft
    created_at: str
    updated_at: str
