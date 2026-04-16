from django.conf import settings


def google_analytics(request):
    google_analytics_id = getattr(settings, "GOOGLE_ANALYTICS_ID", "")

    return {
        "google_analytics_id": google_analytics_id,
        "google_analytics_enabled": bool(google_analytics_id) and not settings.DEBUG,
    }