"""Custom exceptions for Urja portal client and services."""

class UrjaError(Exception):
    """Base exception for Urja platform."""
    pass


class UrjaAuthenticationError(UrjaError):
    """Raised when authentication against Urja portal fails."""
    pass


class UrjaSessionExpiredError(UrjaError):
    """Raised when the session cookie has expired."""
    pass


class UrjaUpstreamError(UrjaError):
    """Raised when upstream Urja portal returns an error code."""
    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.status_code = status_code


class UrjaNotFoundError(UrjaError):
    """Raised when a meter or resource is not found."""
    pass


class UrjaSignatureError(UrjaError):
    """Raised when HMAC signature generation or validation fails."""
    pass
