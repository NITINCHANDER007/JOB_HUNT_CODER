"""
AutoApply AI - EmailToken model.

Stores confirmation emails matched from the user's Gmail inbox after a
job application is submitted.
"""

import uuid
from datetime import datetime

from app import db


class EmailToken(db.Model):
    """A confirmation email fetched via the Gmail API and matched to an application."""

    __tablename__ = "email_tokens"

    # Primary key
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # ── Foreign keys ──────────────────────────────────────────────────────
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nullable: an email may arrive before we can match it to an application
    application_id = db.Column(
        db.String(36),
        db.ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Gmail metadata ────────────────────────────────────────────────────
    gmail_message_id = db.Column(db.String(255), nullable=True)   # Gmail API message ID
    subject = db.Column(db.String(512), nullable=True)
    sender = db.Column(db.String(512), nullable=True)
    received_at = db.Column(db.DateTime, nullable=True)

    # ── Content ───────────────────────────────────────────────────────────
    body_snippet = db.Column(db.Text, nullable=True)              # First ~200 chars of body
    confirmation_link = db.Column(db.String(2048), nullable=True) # Extracted confirmation URL

    # ── Matching ──────────────────────────────────────────────────────────
    matched_company = db.Column(db.String(255), nullable=True)    # Company inferred from email
    is_processed = db.Column(db.Boolean, default=False, nullable=False)

    # ── Timestamps ────────────────────────────────────────────────────────
    # No updated_at – once fetched, email content is treated as immutable
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────
    user = db.relationship("User", back_populates="email_tokens")
    application = db.relationship(
        "Application",
        foreign_keys=[application_id],
        back_populates=None,  # Application.confirmation_email uses a separate FK
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return email token fields as a JSON-safe dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "application_id": self.application_id,
            "gmail_message_id": self.gmail_message_id,
            "subject": self.subject,
            "sender": self.sender,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "body_snippet": self.body_snippet,
            "confirmation_link": self.confirmation_link,
            "matched_company": self.matched_company,
            "is_processed": self.is_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<EmailToken id={self.id} user_id={self.user_id} "
            f"subject={self.subject!r} is_processed={self.is_processed}>"
        )
