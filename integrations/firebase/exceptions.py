"""
Custom exceptions for Firebase Authentication & Phone OTP verification.
"""


class FirebaseOtpError(Exception):
    """Base exception for Firebase Phone OTP operations."""
    pass


class InvalidOtpError(FirebaseOtpError):
    """Raised when submitted OTP code does not match challenge."""
    pass


class OtpExpiredError(FirebaseOtpError):
    """Raised when OTP code or verification session has expired."""
    pass


class OtpAttemptsExceededError(FirebaseOtpError):
    """Raised when too many invalid OTP attempts are made."""
    pass
