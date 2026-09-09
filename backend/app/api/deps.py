from __future__ import annotations

from fastapi import Header, Query, Request

from app.core.constants import DEMO_ADMIN_ID, DEMO_OPERATOR_ID, DEMO_USER_ID
from app.core.enums import UserRole
from app.models import User
from app.services.container import ApplicationContainer


def get_container(request: Request) -> ApplicationContainer:
    return request.app.state.container


async def get_request_actor(
    request: Request,
    actor_header: str | None = Header(default=None, alias="X-Molvest-Role"),
    actor_query: str | None = Query(default=None, alias="role"),
) -> User:
    container = get_container(request)
    try:
        role = UserRole(actor_query or actor_header or UserRole.USER)
    except ValueError:
        role = UserRole.USER
    actor_ids = {
        UserRole.USER: DEMO_USER_ID,
        UserRole.OPERATOR: DEMO_OPERATOR_ID,
        UserRole.ADMIN: DEMO_ADMIN_ID,
    }
    actor_names = {
        UserRole.USER: "Демо пользователь",
        UserRole.OPERATOR: "Демо оператор",
        UserRole.ADMIN: "Демо администратор",
    }
    user_id = actor_ids[role]
    async with container.session_factory() as session:
        user = await session.get(User, user_id)
        if user is None:
            user = User(id=user_id, role=role, display_name=actor_names[role])
            session.add(user)
            await session.commit()
        session.expunge(user)
        return user
