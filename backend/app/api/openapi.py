from __future__ import annotations

from typing import Any

from app.contracts.schemas import ErrorResponse

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "Dialogs",
        "description": (
            "User tickets, messages, attachments, feedback and user-safe SSE."
        ),
    },
    {
        "name": "Operator",
        "description": (
            "Escalation queue, atomic claim, manual templates and operator-only SSE."
        ),
    },
    {
        "name": "Admin Dialogs",
        "description": (
            "Closed-ticket journal, audit, moderation and guarded hard delete."
        ),
    },
    {
        "name": "Knowledge",
        "description": (
            "Knowledge sections and permanent Docling/BGE-M3/Qdrant ingestion."
        ),
    },
    {
        "name": "Prompts",
        "description": "Versioned runtime system prompts.",
    },
    {
        "name": "Settings",
        "description": "Atomic runtime GigaChat and retrieval settings.",
    },
    {
        "name": "Monitoring",
        "description": "Aggregated product and latency metrics.",
    },
]


def _error(description: str, code: str, message: str) -> dict[str, Any]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {
            "application/json": {"example": {"code": code, "message": message}}
        },
    }


API_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: _error(
        "The role or resource guard denied access.", "forbidden", "Недостаточно прав"
    ),
    404: _error(
        "The requested resource does not exist.", "not_found", "Ресурс не найден"
    ),
    409: _error(
        "The command conflicts with current lifecycle state.",
        "conflict",
        "Операция конфликтует с текущим состоянием",
    ),
    422: _error(
        "Request validation or file validation failed.",
        "validation_error",
        "Некорректные данные запроса",
    ),
    503: _error(
        "GigaChat, storage or search provider is unavailable.",
        "service_unavailable",
        "Внешний сервис временно недоступен",
    ),
    500: _error(
        "Unexpected server failure.", "internal_error", "Внутренняя ошибка сервера"
    ),
}

USER_SSE_RESPONSE: dict[str, Any] = {
    "description": (
        "Infinite user-safe stream. The confidence event is emitted after the hidden "
        "structured assessment; when the threshold is passed, answer chunks follow "
        "immediately. Events: confidence, operator_connected, assistant_token, "
        "assistant_done, operator_message, dialog_closed, error. Reconnect and "
        "refetch REST state."
    ),
    "content": {
        "text/event-stream": {
            "schema": {"type": "string"},
            "examples": {
                "assistant_token": {
                    "summary": "Streaming answer token",
                    "value": (
                        "id: 42\nevent: assistant_token\n"
                        'data: {"type":"assistant_token","token":"Проверьте"}\n\n'
                    ),
                },
                "operator_connected": {
                    "summary": "Persisted escalation event",
                    "value": (
                        "id: 43\nevent: operator_connected\n"
                        'data: {"type":"operator_connected","message":{"id":"..."}}\n\n'
                    ),
                },
            },
        }
    },
}

OPERATOR_QUEUE_SSE_RESPONSE: dict[str, Any] = {
    "description": (
        "Infinite operator queue stream. Events: ticket_available, ticket_updated, "
        "ticket_claimed, ticket_closed. Reconnect and refetch both queue scopes."
    ),
    "content": {
        "text/event-stream": {
            "schema": {"type": "string"},
            "example": (
                "id: 51\nevent: ticket_available\n"
                'data: {"type":"ticket_available","dialog":{"id":"..."}}\n\n'
            ),
        }
    },
}

OPERATOR_DIALOG_SSE_RESPONSE: dict[str, Any] = {
    "description": (
        "Infinite operator-only stream. Events: user_message, dialog_closed and "
        "error. Manual templates are returned by the template endpoint."
    ),
    "content": {
        "text/event-stream": {
            "schema": {"type": "string"},
            "examples": {
                "user_message": {
                    "summary": "New user message for the assigned operator",
                    "value": (
                        "id: 61\nevent: user_message\n"
                        'data: {"type":"user_message","message":{"id":"..."}}\n\n'
                    ),
                },
            },
        }
    },
}
