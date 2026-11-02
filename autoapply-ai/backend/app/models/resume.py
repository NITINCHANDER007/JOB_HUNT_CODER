"""
AutoApply AI - Resume model.
"""

import uuid
from datetime import datetime

from app import db


class Resume(db.Model):
    """Represents an uploaded resume file belonging to a user."""

    __tablename__ = "resumes"

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

    # ── File metadata ────────────────────────────────────────────────────
    filename = db.Column(db.String(255), nullable=False)           # stored filename on disk
    original_filename = db.Column(db.String(255), nullable=False)  # original upload name
    file_path = db.Column(db.String(1024), nullable=False)         # absolute path on disk
    file_size = db.Column(db.Integer, nullable=True)               # bytes

    # ── Parsed content ────────────────────────────────────────────────────
    # Full text extracted from the PDF/DOCX
    parsed_text = db.Column(db.Text, nullable=True)

    # Structured data: {name, email, phone, skills, experience, education, …}
    parsed_data = db.Column(db.JSON, nullable=True)

    # ── Flags ─────────────────────────────────────────────────────────────
    # Only one resume per user may be primary at a time (enforced at service level)
    is_primary = db.Column(db.Boolean, default=False, nullable=False)

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ── Relationship ──────────────────────────────────────────────────────
    user = db.relationship("User", back_populates="resumes")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return resume metadata as a JSON-safe dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "filename": self.filename,
            "original_filename": self.original_filename,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "parsed_text": self.parsed_text,
            "parsed_data": self.parsed_data,
            "is_primary": self.is_primary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Resume id={self.id} user_id={self.user_id} filename={self.filename}>"
