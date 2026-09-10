from __future__ import annotations

import asyncio

from starlette.types import ASGIApp, Receive, Scope, Send


class UploadConcurrencyMiddleware:
    def __init__(self, app: ASGIApp, max_concurrency: int) -> None:
        self._app = app
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        path = str(scope.get("path", ""))
        method = scope.get("method")
        is_upload = method == "POST" and (
            path.endswith("/messages")
            or (
                path.startswith("/api/admin/knowledge/sections/")
                and path.endswith("/documents")
            )
        )
        if not is_upload:
            await self._app(scope, receive, send)
            return
        async with self._semaphore:
            await self._app(scope, receive, send)
