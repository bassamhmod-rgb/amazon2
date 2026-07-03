from django.conf import settings
from django.http import HttpResponse


class MobileDevCorsMiddleware:
    """
    Minimal CORS for Flutter Web during local development.

    This is intentionally scoped to /api/mobile/v1/ so it won't affect the rest
    of the site or the existing Access sync endpoints.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith("/api/mobile/v1/") and request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        if request.path.startswith("/api/mobile/v1/"):
            origin = request.headers.get("Origin")
            if settings.DEBUG:
                response["Access-Control-Allow-Origin"] = origin or "*"
            elif origin:
                response["Access-Control-Allow-Origin"] = origin

            response["Vary"] = "Origin"
            response["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
            response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"

        return response

