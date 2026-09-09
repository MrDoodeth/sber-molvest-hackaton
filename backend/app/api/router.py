from fastapi import APIRouter

from app.api.routes import admin, dialogs, knowledge, operator

api_router = APIRouter(prefix="/api")
api_router.include_router(dialogs.router)
api_router.include_router(operator.router)
api_router.include_router(knowledge.router)
api_router.include_router(admin.router)
