"""
Custom exceptions for external RapidAPI providers.
"""


class RapidApiError(Exception):
    """Base exception for RapidAPI integration failures."""
    pass


class PanNotFoundError(RapidApiError):
    """Raised when PAN document record is not found with the provider."""
    pass


class InvalidPanError(RapidApiError):
    """Raised when the PAN document format is invalid."""
    pass


class VehicleNotFoundError(RapidApiError):
    """Raised when a vehicle registration plate is not found in the national registry."""
    pass


class InvalidRegistrationNumberError(RapidApiError):
    """Raised when vehicle registration plate format is invalid."""
    pass


class RateLimitError(RapidApiError):
    """Raised when API provider rate limits or quotas are exceeded."""
    pass


class ProviderUnavailableError(RapidApiError):
    """Raised when the remote API provider encounters a 5xx error or connection timeout."""
    pass
