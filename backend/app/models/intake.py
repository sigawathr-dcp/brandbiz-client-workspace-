"""
app/models/intake.py

ORM models for the client-workspace interview (step 1) — DB redesign, see
the "Client Workspace — Database Redesign" plan.

Replaces app/models/client_intake.py::ClientProfile, which had two
problems: (1) all 8 answers lived in one AES-GCM-encrypted JSON blob
(fields_ciphertext), so there were no per-answer timestamps, no edit
history, every read decrypted all 8, and zero queryability; (2) the
client's position in the interview was a bare integer index into a Python
list (INTAKE_SCRIPT in app/services/client_intake.py) — reordering or
inserting a question would silently reinterpret every already-stored
answer.

The fix: the question script becomes versioned data (IntakeScript ->
IntakeQuestion -> IntakeOption), seeded from INTAKE_SCRIPT as version 1
(migration 0052), and each answer becomes its own row (IntakeAnswer). A
chip pick stores option_id — a queryable foreign key, no ciphertext at
all — and only free-text answers ("Skip" -> type it yourself) are
encrypted. This keeps PLAN.md §7.1's "encrypt client-supplied content at
the boundary" (free text is still client-authored prose) while making the
common case ("how many attendees picked Food & beverage?") a GROUP BY
instead of a decrypt-every-row Python loop.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

VALID_ANSWER_SOURCES: frozenset[str] = frozenset({"chip", "free_text", "edit"})
VALID_USE_MODES: frozenset[str] = frozenset({"match", "feasibility"})


class IntakeScript(Base):
    """One published version of the 8-question script. `engagements.
    intake_script_id` pins which script an engagement's questions/answers
    were given against, so republishing a new version never reinterprets
    an old engagement's stored answers."""

    __tablename__ = "intake_scripts"
    __table_args__ = (
        UniqueConstraint("version", "locale", name="uq_intake_scripts_version_locale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="th")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntakeQuestion(Base):
    __tablename__ = "intake_questions"
    __table_args__ = (
        UniqueConstraint("script_id", "ordinal", name="uq_intake_questions_script_ordinal"),
        UniqueConstraint("script_id", "field_key", name="uq_intake_questions_script_field"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    script_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_scripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    insight: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The interview sheet's columns F/G/H, carried per script version so a
    # reweight publishes a new version instead of editing code (migration
    # 0059). `match_tag` is the case_study_tags.tag_type this question's
    # answer scores against; `weight` is its share of the match score.
    #
    # `use_mode` is one of three (widened from two by migration 0062):
    #   'match'            — weighted into the case-match score.
    #   'feasibility'      — sizes scope and pricing AFTER a plan exists
    #                        (timeframe, budget).
    #   'solution_trigger' — decides that a plan must contain a workstream at
    #                        all (own_commerce); see services/solution_trigger.
    # `weight` is NULL for everything except 'match', enforced by
    # ck_intake_questions_weight_use_mode. Across one script the non-NULL
    # weights sum to 1.000.
    match_tag: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weight: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    # True when the client may answer with SEVERAL chips (the six scoring
    # questions — migration 0064). Multi answers store one intake_answers row
    # per picked option; feasibility/trigger questions stay single-pick.
    multi_select: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    use_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="match"
    )
    dev_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class IntakeOption(Base):
    __tablename__ = "intake_options"
    __table_args__ = (
        UniqueConstraint("question_id", "ordinal", name="uq_intake_options_question_ordinal"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_questions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)  # Thai chip text
    value: Mapped[str] = mapped_column(String(255), nullable=False)  # English stored value
    # Controlled-vocabulary token (app/services/case_taxonomy.py) — the stable
    # identity of an option. Matching keys off this, never off `ordinal` or
    # `label`, so reordering or rewording column D of the sheet in a future
    # script version cannot silently reinterpret a stored answer. NULL on
    # script v1, which predates the tag model.
    tag_value: Mapped[str | None] = mapped_column(String(64), nullable=True)


class IntakeAnswer(Base):
    """Append-only. Editing a field (PATCH /client/intake/fields) stamps
    `superseded_at` on the live row and inserts a new one — real edit
    history, which the old `intake_edited` audit row (details={"field":
    name} only, never old/new) could not provide."""

    __tablename__ = "intake_answers"
    __table_args__ = (
        # Enforced fully in the migration DDL as partial unique indexes
        # (WHERE superseded_at IS NULL) — a field's live answer is either
        # one free-text row or a SET of chip rows with distinct option_ids
        # (multi-select, migration 0064); superseded rows are unlimited.
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    engagement_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagement_steps.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_questions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Denormalized for the common read (resolve "what did they say for
    # `industry`" without a join) — always kept in sync with question_id.
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    option_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("intake_options.id", ondelete="RESTRICT"),
        nullable=True,
    )
    # Free-text only (the "Skip" affordance) — AES-256-GCM, same treatment
    # as app/models/client_intake.py's old fields_ciphertext. NULL when
    # option_id is set: a chip pick needs no ciphertext at all.
    value_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    value_nonce: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    value_tag: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # chip | free_text | edit
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
