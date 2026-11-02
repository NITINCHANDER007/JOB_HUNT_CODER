"""Custom exceptions for adapter errors."""


class CaptchaDetectedError(Exception):
    """Raised when a CAPTCHA challenge is detected on the page."""
    pass


class LoginWallError(Exception):
    """Raised when the page requires login before applying."""
    pass


class UnsupportedFormError(Exception):
    """Raised when the form cannot be extracted or filled."""
    pass


class SubmissionFailedError(Exception):
    """Raised when form submission fails or no confirmation detected."""
    pass


class RateLimitError(Exception):
    """Raised when the site rate-limits our requests."""
    pass


class NavigationError(Exception):
    """Raised when page navigation fails or times out."""
    pass


class ExpiredJobError(Exception):
    """Raised when a job posting has closed, expired, or is no longer available."""
    pass


class MissingInformationError(Exception):
    """Raised when required form fields cannot be answered from the user profile."""

    def __init__(self, message: str, missing_fields: list = None):
        super().__init__(message)
        self.missing_fields = missing_fields or []


class ResumeUploadError(Exception):
    """Raised when resume file upload fails after retrying."""
    pass


class DuplicateApplicationError(Exception):
    """Raised when the user has already applied to this exact role or company."""
    pass


class ReviewApprovalRequiredError(Exception):
    """Raised when application review is ready and requires user approval before final submission."""

    def __init__(self, message: str, review_details: dict = None):
        super().__init__(message)
        self.review_details = review_details or {}
