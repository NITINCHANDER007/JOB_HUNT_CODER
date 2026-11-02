"""
AutoApply AI - Models package.
Import all models here so Flask-Migrate can detect them.
"""

from app import db
from app.models.user import User
from app.models.profile import Profile
from app.models.resume import Resume
from app.models.application import Application, ApplicationLog, ApplicationStatus
from app.models.email_token import EmailToken

__all__ = [
    "db",
    "User",
    "Profile",
    "Resume",
    "Application",
    "ApplicationLog",
    "ApplicationStatus",
    "EmailToken",
]
