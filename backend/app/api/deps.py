from __future__ import annotations

from typing import Annotated

from fastapi import Request, Security
from fastapi.security import APIKeyCookie

from app.core.auth import decode_access_token
from app.core.errors import UnauthorizedError
from app.models import User
from app.services.container import ApplicationContainer

cookie_jwt_scheme = APIKeyCookie(
    name="molvest_session",
    scheme_name="CookieJWT",
    description=(
        "JWT access token in an HttpOnly cookie. Use demo login when "
        "DEMO_AUTH_ENABLED=true; Swagger then reuses the browser cookie."
    ),
    auto_error=False,
)


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


async def get_current_user(
    request: Request,
    cookie_token: Annotated[str | None, Security(cookie_jwt_scheme)],
) -> User:
    container = get_container(request)
    token = cookie_token or request.cookies.get(container.settings.auth_cookie_name)
    if not token:
        raise UnauthorizedError()
    user_id = decode_access_token(token, container.settings)
    if user_id is None:
        raise UnauthorizedError("Сессия недействительна или истекла")
    async with container.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            raise UnauthorizedError("Пользователь сессии не найден")
        session.expunge(user)
        return user
