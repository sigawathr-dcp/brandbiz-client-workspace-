import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import ENUM as PgEnum, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# References type created by Alembic 0001_baseline — do not recreate it
_audit_action_pg = PgEnum(
    "login", "logout",
    "message_sent", "message_received",
    "model_blocked", "pii_detected", "tier_blocked", "quota_exceeded",
    "reveal_requested", "reveal_approved", "reveal_denied", "reveal_viewed",
    "admin_user_created", "admin_role_changed", "admin_quota_changed",
    "admin_permission_changed", "file_uploaded", "rag_query",
    "consent_acknowledged",
    "image_requested", "image_generated",
    # n8n integration (0009)
    "n8n_triggered",
    # Studio actions (0014)
    "studio_image_denied", "studio_generate_requested", "studio_image_generated",
    "studio_video_denied", "studio_video_generated", "studio_video_failed",
    "studio_generate_mocked",
    # Music studio (0017)
    "studio_music_denied", "studio_music_generated", "studio_music_failed",
    # AI Agents (0019)
    "agent_created", "agent_updated", "agent_deleted",
    # Password login (0023)
    "login_failed",
    # Obsidian vault sync (0027)
    "vault_note_ingested", "vault_note_updated", "vault_note_deleted",
    "vault_note_quarantined",
    # Admin-configurable vault connection + sync (0028)
    "vault_connection_updated", "vault_sync_triggered",
    "vault_sync_completed", "vault_sync_failed",
    # Background agent tasks (0031)
    "agent_task_submitted", "agent_task_running", "agent_task_succeeded",
    "agent_task_failed", "agent_task_cancelled",
    # Hermes host-setup script download (0034)
    "hermes_setup_script_downloaded",
    # Hermes one-click host jobs (0035)
    "hermes_host_job_created", "hermes_helper_script_downloaded",
    # Skills (0037)
    "skill_created", "skill_updated", "skill_deleted", "skill_invoked",
    # Client Workspaces (0039, D21/D22)
    "client_invited", "client_redeemed", "intake_answered", "research_run",
    "case_matched", "plan_created", "plan_updated", "plan_shared",
    "plan_exported", "lead_submitted",
    # Client workspace redesign (0045, PLAN.md Task 5.10)
    "plan_rated",
    # Editable company profile (0048, PLAN.md Task 5.11)
    "intake_edited",
    # D14 message retention (0047) — added to the PG type there, but
    # missing from this ORM-side label list until now; harmless at runtime
    # (SQLAlchemy doesn't validate raw-string PG enum values by default)
    # but the two were out of sync. See app/services/retention.py.
    "messages_purged",
    # Client Workspace DB redesign (0050) — a seat starting a fresh
    # engagement (POST /client/engagements), distinct from the original
    # client_redeemed (invite -> first seat) event.
    "engagement_started",
    name="audit_action",
    create_type=False,
)


class AuditLog(Base):
    __tablename__ = "audit_log"

    # Composite PK required by Postgres partitioned table (id, created_at)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now()
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(_audit_action_pg, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
