from django.apps import AppConfig


class UsuarioConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "usuario"
    verbose_name = "Usuário"

    def ready(self):
        import usuario.signals  # noqa: F401
