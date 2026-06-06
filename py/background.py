"""Helper for fire-and-forget background tasks.

``asyncio`` only keeps a weak reference to a task, so a task created without
keeping its result may be garbage-collected before it finishes.  ``spawn``
holds a strong reference until the task completes.
"""

import asyncio

_background_tasks: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    """Schedule ``coro`` and keep a strong reference until it finishes."""
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
