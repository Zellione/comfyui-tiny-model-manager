from aiohttp import web

from ..services import backend_notifier


def add_notification_routes(routes):

    @routes.get("/tiny-model-manager/api/notifications")
    async def get_notifications(request):
        try:
            return web.json_response({"success": True, "data": backend_notifier.flush()})
        except Exception as exc:
            return web.json_response({"success": False, "error": str(exc)}, status=500)
