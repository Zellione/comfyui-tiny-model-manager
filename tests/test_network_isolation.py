"""Regression tests for the test-suite network guard (issue #118).

A real DNS lookup runs in asyncio's default ``ThreadPoolExecutor``, and pytest-asyncio closes
its per-test loop with ``asyncio.Runner.close()``, which calls ``loop.shutdown_default_executor()``
without a timeout.  A resolver that stalls therefore wedges teardown forever — the intermittent
backend CI hang.  ``block_network`` in ``conftest.py`` makes that failure loud and immediate;
these tests keep it honest.
"""

import socket

import pytest


def test_external_dns_is_blocked():
    with pytest.raises(RuntimeError, match="issue #118"):
        socket.getaddrinfo("example.com", 443)


def test_external_connect_is_blocked():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="issue #118"):
            sock.connect(("93.184.216.34", 80))
    finally:
        sock.close()


def test_loopback_dns_still_allowed():
    assert socket.getaddrinfo("127.0.0.1", 80)


async def test_aiohttp_test_server_still_works(aiohttp_client):
    """The guard must not break aiohttp's loopback test server, which every route test uses."""
    from aiohttp import web

    async def handler(_request):
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/ping", handler)
    client = await aiohttp_client(app)

    resp = await client.get("/ping")
    assert resp.status == 200
    assert (await resp.json())["ok"] is True
