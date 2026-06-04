from ..services import backend_notifier
from ._helpers import json_route, ok


def add_notification_routes(routes):

    @routes.get("/tiny-model-manager/api/notifications")
    @json_route
    async def get_notifications(request):
        return ok(backend_notifier.flush())
