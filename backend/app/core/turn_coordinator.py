from __future__ import annotations

import uuid
from dataclasses import dataclass

AI_TURN_ADMISSION_LOCK_KEY = 712031043


@dataclass(frozen=True, slots=True)
class ActiveTurn:
    dialog_id: uuid.UUID
    message_id: uuid.UUID


class TurnCoordinator:
    """Reject overlapping AI turns inside one backend process.

    The synchronous state transition is safe because callers run on the same
    asyncio event loop and no await occurs between checking and setting it.
    PostgreSQL admission locking complements this coordinator across workers.
    """

    def __init__(self) -> None:
        self._active: ActiveTurn | None = None

    @property
    def active(self) -> ActiveTurn | None:
        return self._active

    def try_acquire(self, dialog_id: uuid.UUID, message_id: uuid.UUID) -> bool:
        current = self._active
        if current is not None:
            return current.dialog_id == dialog_id and current.message_id == message_id
        self._active = ActiveTurn(dialog_id=dialog_id, message_id=message_id)
        return True

    def release(self, dialog_id: uuid.UUID, message_id: uuid.UUID) -> None:
        current = self._active
        if current is not None and (
            current.dialog_id == dialog_id and current.message_id == message_id
        ):
            self._active = None
