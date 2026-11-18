class AuthenticationError(Exception):
    """Base class for authentication-related errors."""
    pass


class UserNotFoundError(AuthenticationError):
    """Raised when a user is not found in the authentication system."""
    pass


class WrongCredentialsError(AuthenticationError):
    """Raised when the provided credentials are incorrect."""
    pass
