"""In-memory queue of backend-originated UI notifications (toasts)."""

import uuid

_pending: list[dict] = []


def push(type_: str, message: str) -> None:
    _pending.append({"id": uuid.uuid4().hex, "type": type_, "message": message})


def flush() -> list[dict]:
    items = list(_pending)
    _pending.clear()
    return items
