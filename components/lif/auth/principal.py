"""The one auth contract shared by every strategy and the middleware (ADR 0007).

A strategy inspects a request and returns:

- a ``Principal`` when it authenticated the caller,
- ``None`` when the request doesn't carry its kind of credential (try the next strategy),
- or raises ``AuthError`` when it carries its kind of credential but that credential is
  invalid (reject, keeping the specific message).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import HTTPException, status
from starlette.requests import Request


@dataclass(frozen=True)
class Principal:
    """An authenticated caller: a stable id, the strategy that authenticated it, and any claims."""

    id: str
    method: str
    claims: dict[str, Any] = field(default_factory=dict)


Strategy = Callable[[Request], Optional[Principal]]


class AuthError(HTTPException):
    """A credential was presented but is invalid.

    Subclasses ``HTTPException`` so code that already handles FastAPI's 401s keeps
    working while callers migrate to the strategies.
    """

    def __init__(self, detail: str, status_code: int = status.HTTP_401_UNAUTHORIZED, challenge: str = "Bearer") -> None:
        super().__init__(status_code=status_code, detail=detail, headers={"WWW-Authenticate": challenge})
