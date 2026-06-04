"""Shared helpers for aiohttp route handlers.

Every API route returns a JSON envelope: ``{"success": True, ...}`` on success or
``{"success": False, "error": "..."}`` on failure. These helpers remove the per-route
boilerplate for that envelope and for the catch-all ``status=500`` handler that wrapped
almost every route body.
"""

import functools

from aiohttp import web

_UNSET = object()


def ok(data=_UNSET, **extra) -> web.Response:
    """Build a success envelope.

    ``ok(result)``      -> ``{"success": True, "data": result}``
    ``ok()``            -> ``{"success": True}``
    ``ok(new_path=p)``  -> ``{"success": True, "new_path": p}``
    """
    payload: dict = {"success": True}
    if data is not _UNSET:
        payload["data"] = data
    payload.update(extra)
    return web.json_response(payload)


def err(message: str, status: int = 500) -> web.Response:
    """Build a failure envelope with the given HTTP status."""
    return web.json_response({"success": False, "error": message}, status=status)


def json_route(handler):
    """Wrap a route handler so any uncaught exception becomes a 500 error envelope.

    Handlers can still ``return err(..., status=400)`` for expected client errors;
    only unexpected exceptions are translated into ``{"success": False, "error": ...}``.
    """

    @functools.wraps(handler)
    async def wrapper(request):
        try:
            return await handler(request)
        except Exception as exc:
            return err(str(exc))

    return wrapper
