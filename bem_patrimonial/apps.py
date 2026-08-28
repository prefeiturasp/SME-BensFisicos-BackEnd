from django.apps import AppConfig


class BemPatrimonialConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "bem_patrimonial"
    verbose_name = "Bem Patrimonial"
    ordering = [
        "bempatrimonial",
        "movimentacaobempatrimonial",
        "transferenciabempatrimonial",
        "baixafisicabempatrimonial",
        "nbbpm",
    ]

    def ready(self):
        # Respeita AppConfig.ordering para ordenar modelos no admin
        # sem mudar verbose_name; fallback alfabético para apps sem ordering
        from django.apps import apps
        from django.contrib import admin

        original = admin.AdminSite.get_app_list

        # evita patch duplo em reload
        if getattr(original, "_ordering_patched", False):
            return

        def get_app_list_patched(self, request, app_label=None):
            app_dict = self._build_app_dict(request, app_label)
            app_list = sorted(app_dict.values(), key=lambda x: x["name"].lower())
            for app in app_list:
                try:
                    app_config = apps.get_app_config(app["app_label"])
                    ordering = getattr(app_config, "ordering", None)
                except LookupError:
                    ordering = None
                if ordering:
                    order_map = {name.lower(): idx for idx, name in enumerate(ordering)}

                    def sort_key(m, order_map=order_map):
                        key = m["object_name"].lower()
                        idx = order_map.get(key, 999)
                        return (idx, m["name"].lower())

                    app["models"].sort(key=sort_key)
                else:
                    app["models"].sort(key=lambda x: x["name"])
            return app_list

        get_app_list_patched._ordering_patched = True
        admin.AdminSite.get_app_list = get_app_list_patched
