from dados_comuns.context import set_user


class AuditUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            set_user(getattr(request, "user", None))
            return self.get_response(request)
        finally:
            set_user(None)
