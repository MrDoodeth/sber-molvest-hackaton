from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from app.api.deps import get_container, get_current_user
from app.api.openapi import PROTECTED_RESPONSES
from app.contracts.mappers import current_user
from app.contracts.schemas import CurrentUser, DemoLoginRequest
from app.core.auth import create_access_token
from app.core.constants import DEMO_ADMIN_ID, DEMO_OPERATOR_ID, DEMO_USER_ID
from app.core.enums import UserRole
from app.core.errors import NotFoundError
from app.models import User
from app.services.container import ApplicationContainer

router = APIRouter()


@router.get(
    "/me",
    response_model=CurrentUser,
    tags=["Auth"],
    summary="Get current session user",
    responses=PROTECTED_RESPONSES,
)
async def me(user: User = Depends(get_current_user)) -> CurrentUser:
    return current_user(user)


@router.post(
    "/auth/demo-login",
    response_model=CurrentUser,
    tags=["Auth"],
    summary="Login as a seeded demo role",
    description=(
        "Available only outside production. In production this endpoint returns "
        "`404`. It selects the seeded user for the requested role and "
        "sets the HttpOnly JWT cookie; it is not a production identity provider."
    ),
    responses=PROTECTED_RESPONSES,
)
async def demo_login(
    payload: DemoLoginRequest,
    response: Response,
    container: ApplicationContainer = Depends(get_container),
) -> CurrentUser:
    if not container.settings.demo_auth_enabled:
        raise NotFoundError("Demo auth отключён")
    ids = {
        UserRole.USER: DEMO_USER_ID,
        UserRole.OPERATOR: DEMO_OPERATOR_ID,
        UserRole.ADMIN: DEMO_ADMIN_ID,
    }
    async with container.session_factory() as session:
        user = await session.get(User, ids[UserRole(payload.role)])
        if user is None or user.role != payload.role:
            raise NotFoundError("Demo user не найден; выполните seed")
    token = create_access_token(user.id, container.settings)
    response.set_cookie(
        key=container.settings.auth_cookie_name,
        value=token,
        max_age=container.settings.jwt_ttl_minutes * 60,
        httponly=True,
        secure=container.settings.auth_cookie_secure,
        samesite=container.settings.auth_cookie_samesite,
        path="/",
    )
    return current_user(user)


@router.post(
    "/auth/logout",
    status_code=204,
    response_model=None,
    tags=["Auth"],
    summary="Delete the session cookie",
)
async def logout(
    response: Response,
    container: ApplicationContainer = Depends(get_container),
) -> None:
    response.delete_cookie(
        key=container.settings.auth_cookie_name,
        path="/",
        secure=container.settings.auth_cookie_secure,
        httponly=True,
        samesite=container.settings.auth_cookie_samesite,
    )
