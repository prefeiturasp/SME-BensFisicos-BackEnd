# usuario/middleware.py
from django.shortcuts import redirect
from django.urls import reverse
from urllib.parse import urlencode

ADMIN_PREFIX = "/admin/"
PASSWORD_CHANGE_URLNAME = "password_change"


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        path = request.path

        if (
            user is not None
            and getattr(user, "is_authenticated", False)
            and path.startswith(ADMIN_PREFIX)
        ):
            if path.startswith("/admin/password-change/"):
                return self.get_response(request)

            if request.session.get("force_pw_change_first_admin"):
                request.session.pop("force_pw_change_first_admin", None)
                params = urlencode({"next": request.get_full_path()})
                return redirect(f"{reverse(PASSWORD_CHANGE_URLNAME)}?{params}")

            if getattr(user, "must_change_password", False):
                params = urlencode({"next": request.get_full_path()})
                return redirect(f"{reverse(PASSWORD_CHANGE_URLNAME)}?{params}")

        return self.get_response(request)
