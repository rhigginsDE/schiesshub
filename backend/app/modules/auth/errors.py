"""Fehler des Moduls. Die Meldungen sind für Anwender gedacht und landen in `detail`."""

from fastapi import HTTPException, status

from app.core.errors import CodedError

DEVICE_UNKNOWN = "device_unknown"
DEVICE_REVOKED = "device_revoked"
SESSION_EXPIRED = "session_expired"
LOGIN_REQUIRED = "login_required"
LOGIN_FAILED = "login_failed"
# 409: Berechtigungsprüfung kann (noch) nicht eingeschaltet werden, siehe GET /auth/enforcement.
ENFORCEMENT_BLOCKED = "enforcement_blocked"


class NotFoundError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class InvalidError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


class UnauthorizedError(CodedError):
    """HTTP 401 mit `code`, damit die Oberfläche die Fälle unterscheiden kann:

    - `device_unknown`: Gerät nie gekoppelt, entfernt oder Cookie fehlt
    - `device_revoked`: Gerät gesperrt
    - `session_expired`: Anmeldung abgelaufen oder beendet (z. B. nach PIN-Wechsel)
    - `login_required`: Gerät gekoppelt, aber niemand angemeldet (und keine nutzbare Standardrolle)
    - `login_failed`: Benutzer oder PIN stimmt nicht
    """

    def __init__(self, detail: str, code: str) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail, code)


class ForbiddenError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, detail)


class LockedError(HTTPException):
    def __init__(self, detail: str, retry_after_seconds: int) -> None:
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail,
            headers={"Retry-After": str(max(retry_after_seconds, 1))},
        )
