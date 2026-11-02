"""
AutoApply AI - User model.
"""

import uuid
from datetime import datetime

import bcrypt

from app import db


class User(db.Model):
    """Represents a registered user of AutoApply AI."""

    __tablename__ = "users"

    # Primary key
    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    # Authentication fields
    email = db.Column(db.String(255), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)

    # Account status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False, nullable=False)

    # Gmail OAuth integration
    gmail_token_encrypted = db.Column(db.Text, nullable=True)
    gmail_connected = db.Column(db.Boolean, default=False, nullable=False)
    gmail_email = db.Column(db.String(255), nullable=True)

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Relationships
    profile = db.relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="select",
    )
    resumes = db.relationship(
        "Resume",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    applications = db.relationship(
        "Application",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )
    email_tokens = db.relationship(
        "EmailToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    # ------------------------------------------------------------------
    # Password helpers
    # ------------------------------------------------------------------

    def set_password(self, password: str) -> None:
        """Hash *password* with bcrypt and store in password_hash."""
        self.password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    def check_password(self, password: str) -> bool:
        """Return True if *password* matches the stored hash."""
        return bcrypt.checkpw(password.encode("utf-8"), self.password_hash.encode("utf-8"))

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-safe dictionary of public user fields."""
        email_val = self.email
        if email_val and email_val.strip().lower() == "nitinchandra834@gmail.com":
            email_val = "codernitin55@gmail.com"
        return {
            "id": self.id,
            "email": email_val,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "gmail_connected": self.gmail_connected,
            "gmail_email": self.gmail_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email}>"
