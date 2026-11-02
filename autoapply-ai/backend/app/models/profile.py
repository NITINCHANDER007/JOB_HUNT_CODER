"""
AutoApply AI - Profile model.
"""

import uuid
from datetime import datetime

from app import db


class Profile(db.Model):
    """Extended profile data for a user — used for auto-filling job applications."""

    __tablename__ = "profiles"

    # Primary key
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Foreign key – one profile per user
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Contact & location ──────────────────────────────────────────────
    phone = db.Column(db.String(50), nullable=True)
    location = db.Column(db.String(255), nullable=True)  # "City, State, Country"

    # ── Online presence ─────────────────────────────────────────────────
    linkedin_url = db.Column(db.String(512), nullable=True)
    github_url = db.Column(db.String(512), nullable=True)
    portfolio_url = db.Column(db.String(512), nullable=True)

    # ── Career info ──────────────────────────────────────────────────────
    years_of_experience = db.Column(db.Integer, nullable=True)
    current_title = db.Column(db.String(255), nullable=True)

    # ── Structured JSON fields ───────────────────────────────────────────
    # [{degree, field, school, graduation_year, gpa}]
    education = db.Column(db.JSON, nullable=True)

    # ["Python", "React", "SQL", ...]
    skills = db.Column(db.JSON, nullable=True)

    # [{company, title, start_date, end_date, description, current}]
    experience = db.Column(db.JSON, nullable=True)

    # [{name, issuer, year}]
    certifications = db.Column(db.JSON, nullable=True)

    # [{language, proficiency}]
    languages = db.Column(db.JSON, nullable=True)

    # ── Work preferences ─────────────────────────────────────────────────
    notice_period = db.Column(db.String(100), nullable=True)   # e.g. "2 weeks"
    expected_ctc = db.Column(db.String(100), nullable=True)    # e.g. "80000 USD/year"
    current_ctc = db.Column(db.String(100), nullable=True)
    work_authorization = db.Column(db.String(100), nullable=True)  # "US Citizen", "H1B" …
    willing_to_relocate = db.Column(db.Boolean, nullable=True)
    remote_preference = db.Column(db.String(50), nullable=True)   # "Remote" | "Hybrid" | …

    # ── EEO / diversity fields (all optional) ────────────────────────────
    gender = db.Column(db.String(50), nullable=True)
    ethnicity = db.Column(db.String(100), nullable=True)
    veteran_status = db.Column(db.String(100), nullable=True)
    disability_status = db.Column(db.String(100), nullable=True)
    pronouns = db.Column(db.String(50), nullable=True)

    # ── Bio ──────────────────────────────────────────────────────────────
    summary = db.Column(db.Text, nullable=True)

    # ── Timestamps ───────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ── Relationship ─────────────────────────────────────────────────────
    user = db.relationship("User", back_populates="profile")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return all profile fields as a JSON-safe dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "phone": self.phone,
            "location": self.location,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "portfolio_url": self.portfolio_url,
            "years_of_experience": self.years_of_experience,
            "current_title": self.current_title,
            "education": self.education,
            "skills": self.skills,
            "experience": self.experience,
            "certifications": self.certifications,
            "languages": self.languages,
            "notice_period": self.notice_period,
            "expected_ctc": self.expected_ctc,
            "current_ctc": self.current_ctc,
            "work_authorization": self.work_authorization,
            "willing_to_relocate": self.willing_to_relocate,
            "remote_preference": self.remote_preference,
            "gender": self.gender,
            "ethnicity": self.ethnicity,
            "veteran_status": self.veteran_status,
            "disability_status": self.disability_status,
            "pronouns": self.pronouns,
            "summary": self.summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Profile id={self.id} user_id={self.user_id}>"
