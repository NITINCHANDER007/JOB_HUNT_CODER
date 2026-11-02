"""
AutoApply AI - Application and ApplicationLog models.
"""

import enum
import uuid
from datetime import datetime

from app import db


class ApplicationStatus(str, enum.Enum):
    """Lifecycle states for a job application attempt."""

    QUEUED = "QUEUED"              # Pending
    APPLYING = "APPLYING"          # In Progress
    SUBMITTED = "SUBMITTED"        # Submitted – Unverified
    APPLIED = "APPLIED"            # Applied – Verified
    FAILED = "FAILED"              # Failed
    NEEDS_ACTION = "NEEDS_ACTION"  # Manual Intervention Required


STATUS_DISPLAY_MAP = {
    "QUEUED": "Pending",
    "APPLYING": "In Progress",
    "SUBMITTED": "Submitted – Unverified",
    "APPLIED": "Applied – Verified",
    "FAILED": "Failed",
    "NEEDS_ACTION": "Manual Intervention Required",
}


class Application(db.Model):
    """Represents a single job application submitted (or to be submitted) by a user."""

    __tablename__ = "applications"

    # Primary key
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign key
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Job / posting info ────────────────────────────────────────────────
    url = db.Column(db.Text, nullable=False)                  # The job application URL
    company = db.Column(db.String(255), nullable=True)        # Scraped company name
    role = db.Column(db.String(255), nullable=True)           # Scraped job title
    job_description = db.Column(db.Text, nullable=True)       # Full JD text

    # Platform identifier: greenhouse | lever | ashby | workable | smartrecruiters | generic
    platform = db.Column(db.String(50), nullable=True)
    resume_used = db.Column(db.String(255), nullable=True)

    # ── Status ────────────────────────────────────────────────────────────
    status = db.Column(
        db.Enum(ApplicationStatus),
        default=ApplicationStatus.QUEUED,
        nullable=False,
        index=True,
    )
    error_message = db.Column(db.Text, nullable=True)         # Failure / needs-action reason

    # ── Evidence ──────────────────────────────────────────────────────────
    screenshot_path = db.Column(db.String(1024), nullable=True)   # Disk path to screenshot
    screenshot_url = db.Column(db.String(512), nullable=True)     # Relative URL to serve it
    confirmation_url = db.Column(db.String(1024), nullable=True)  # Post-submit confirmation page

    # ── Email token link ──────────────────────────────────────────────────
    confirmation_email_id = db.Column(
        db.String(36),
        db.ForeignKey("email_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Celery / retry ────────────────────────────────────────────────────
    retry_count = db.Column(db.Integer, default=0, nullable=False)
    celery_task_id = db.Column(db.String(255), nullable=True)

    # ── AI / form data ────────────────────────────────────────────────────
    # Raw form fields scraped from the page
    form_fields_json = db.Column(db.JSON, nullable=True)
    # Gemini-generated label → value mapping
    ai_mapping_json = db.Column(db.JSON, nullable=True)
    # Action / chatbot details (missing fields, captcha, login, verification)
    action_details_json = db.Column(db.JSON, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────
    user = db.relationship("User", back_populates="applications")
    logs = db.relationship(
        "ApplicationLog",
        back_populates="application",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ApplicationLog.created_at",
    )
    confirmation_email = db.relationship(
        "EmailToken",
        foreign_keys=[confirmation_email_id],
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return all application fields as a JSON-safe dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "url": self.url,
            "company": self.company,
            "role": self.role,
            "job_description": self.job_description,
            "platform": self.platform,
            "resume_used": self.resume_used,
            "status": self.status.value if self.status else None,
            "status_display": STATUS_DISPLAY_MAP.get(self.status.value if self.status else "", self.status.value if self.status else "Pending"),
            "error_message": self.error_message,
            "screenshot_path": self.screenshot_path,
            "screenshot_url": self.screenshot_url,
            "confirmation_url": self.confirmation_url,
            "confirmation_email_id": self.confirmation_email_id,
            "retry_count": self.retry_count,
            "celery_task_id": self.celery_task_id,
            "form_fields_json": self.form_fields_json,
            "ai_mapping_json": self.ai_mapping_json,
            "action_details": self.action_details_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Application id={self.id} user_id={self.user_id} "
            f"status={self.status} company={self.company}>"
        )


class ApplicationLog(db.Model):
    """Audit log entries for a single application run."""

    __tablename__ = "application_logs"

    # Primary key
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign key
    application_id = db.Column(
        db.String(36),
        db.ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Log entry
    level = db.Column(db.String(10), nullable=False)   # "INFO" | "WARNING" | "ERROR"
    message = db.Column(db.Text, nullable=False)
    extra_data = db.Column(db.JSON, nullable=True)     # Optional structured context

    # Timestamp (no updated_at – logs are immutable)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Relationship
    application = db.relationship("Application", back_populates="logs")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return log entry as a JSON-safe dictionary."""
        return {
            "id": self.id,
            "application_id": self.application_id,
            "level": self.level,
            "message": self.message,
            "extra_data": self.extra_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ApplicationLog id={self.id} application_id={self.application_id} "
            f"level={self.level}>"
        )
