from __future__ import annotations


class ApplicationError(Exception):
    """Expected application error that can be safely returned to clients."""

    status_code = 400
    code = "application_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ApplicationError):
    status_code = 404
    code = "not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "conflict"


class DatabaseError(ApplicationError):
    status_code = 500
    code = "database_error"


class AiUnavailableError(ApplicationError):
    status_code = 503
    code = "ai_unavailable"
