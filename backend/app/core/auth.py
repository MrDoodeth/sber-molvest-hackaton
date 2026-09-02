from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from jwt import InvalidTokenError

from app.core.config import Settings

JWT_ISSUER = "molvest-support-backend"
JWT_AUDIENCE = "molvest-support-spa"


def create_access_token(user_id: uuid.UUID, settings: Settings) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=settings.jwt_ttl_minutes),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str, settings: Settings) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iss", "aud", "exp", "iat"]},
        )
        return uuid.UUID(str(payload["sub"]))
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
