from django.conf import settings


def google_analytics(request):
    google_analytics_id = getattr(settings, "GOOGLE_ANALYTICS_ID", "")
    is_admin_request = getattr(request, "path", "").startswith("/admin/")

    return {
        "google_analytics_id": google_analytics_id,
        "google_analytics_enabled": bool(google_analytics_id)
        and not settings.DEBUG
        and is_admin_request,
    }