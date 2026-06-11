"""Unit tests for py/routes/_helpers.py — JSON envelope and error wrapping."""

import json

from py.routes._helpers import json_route


class _FakeResponse:
    pass


async def test_json_route_does_not_leak_exception_text():
    @json_route
    async def handler(_request):
        raise RuntimeError("/home/secret/path leaked internal detail")

    resp = await handler(object())

    assert resp.status == 500
    body = json.loads(resp.body)
    assert body["success"] is False
    # The raw exception text (paths, internals) must not reach the client.
    assert "secret" not in body["error"]
    assert "leaked internal detail" not in body["error"]


async def test_json_route_passes_through_normal_response():
    sentinel = _FakeResponse()

    @json_route
    async def handler(_request):
        return sentinel

    resp = await handler(object())
    assert resp is sentinel
