"""Fehler des Moduls. Die Meldungen sind für Anwender gedacht und landen in `detail`."""

from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConflictError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_409_CONFLICT, detail)


class InvalidError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


class UnauthorizedError(HTTPException):
    def __init__(self, detail: str) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, detail)


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
