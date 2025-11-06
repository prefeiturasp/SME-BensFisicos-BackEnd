from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_admin_listfilter_dropdown.filters import DropdownFilter
from rangefilter.filters import DateRangeFilter
from django.shortcuts import redirect
from django.urls import reverse
from usuario.models import Usuario
from dados_comuns.models import UnidadeAdministrativa


# TODO ajusta retorno de usuarios conforme GRUPO
class CustomUserModelAdmin(UserAdmin):
    model = Usuario
    list_display = (
        "nome",
        "email",
        "unidade_administrativa",
        "get_grupo",
    )
    search_fields = ("nome",)
    search_help_text = "Pesquise por nome."
    ordering = ("unidade_administrativa__codigo",)

    list_filter = UserAdmin.list_filter + (
        ("unidade_administrativa__sigla", DropdownFilter),
        ("date_joined", DateRangeFilter),
    )

    fieldsets = (
        ("Acesso", {"fields": ("username", "password")}),
        (
            "Informações pessoais",
            {
                "fields": (
                    "nome",
                    "rf",
                    "email",
                    "unidade_administrativa",
                )
            },
        ),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "groups",
                )
            },
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        ("Acesso", {"fields": ("username", "password1", "password2")}),
        (
            "Informações pessoais",
            {
                "fields": (
                    "nome",
                    "rf",
                    "email",
                    "unidade_administrativa",
                )
            },
        ),
        (
            "Permissões",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "groups",
                )
            },
        ),
        ("Datas importantes", {"fields": ("last_login", "date_joined")}),
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("username",)
        return self.readonly_fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unidade_administrativa":
            kwargs["queryset"] = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description="Grupo")
    def get_grupo(self, obj):
        if obj.is_gestor_patrimonio:
            return "GESTOR_PATRIMONIO"
        elif obj.is_operador_inventario:
            return "OPERADOR_INVENTARIO"
        return "-"


admin.site.register(Usuario, CustomUserModelAdmin)
