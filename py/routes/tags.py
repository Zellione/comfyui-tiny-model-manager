from ..db import model_repo
from ._helpers import json_route, ok


async def _search_tags(request):
    q = request.rel_url.query.get("q", "").strip()
    if not q:
        return ok([])
    tags = await model_repo.search_tags(q)
    return ok(tags)


def add_tag_routes(routes):
    routes.get("/tiny-model-manager/api/tags")(json_route(_search_tags))
