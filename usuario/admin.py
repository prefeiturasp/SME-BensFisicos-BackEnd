from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django_admin_listfilter_dropdown.filters import DropdownFilter
from rangefilter.filters import DateRangeFilter
from django.shortcuts import redirect
from django.urls import reverse
from usuario.models import Usuario
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria


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
                    "unidade_orcamentaria",
                    "unidade_administrativa",
                )
            },
        ),
        ("Permissões", {"fields": ("is_active", "is_staff", "groups")}),
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
                    "unidade_orcamentaria",
                    "unidade_administrativa",
                )
            },
        ),
        ("Permissões", {"fields": ("is_active", "is_staff", "groups")}),
    )

    class Media:
        css = {"all": ("css/hide_crud_icons.css",)}
        js = ("admin/usuario_uo_ua.js",)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            base = self.add_fieldsets
        else:
            base = self.fieldsets
            
        if request.user.is_superuser:
            base = base + (
                (
                    "Super-admin",
                    {"fields": ("is_superuser",)},
                ),
            )
        return base

    def get_add_fieldsets(self, request):
        base = self.add_fieldsets
        if request.user.is_superuser:
            base = base + (
                (
                    "Super-admin",
                    {"fields": ("is_superuser",)},
                ),
            )
        return base

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("username",)
        return self.readonly_fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unidade_orcamentaria":

            if not request.user.is_superuser:
                if request.user.unidade_orcamentaria_id:
                    kwargs["queryset"] = UnidadeOrcamentaria.objects.filter(
                        pk=request.user.unidade_orcamentaria_id
                    )
                else:
                    kwargs["queryset"] = UnidadeOrcamentaria.objects.none()
            else:
                kwargs["queryset"] = UnidadeOrcamentaria.objects.all()

        if db_field.name == "unidade_administrativa":
            qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )

            uo_id = None

            if request.method == "POST":
                uo_id = request.POST.get("unidade_orcamentaria") or None

            if not uo_id:
                uo_id = request.GET.get("unidade_orcamentaria") or None

            if (
                not uo_id
                and hasattr(request, "_obj_usuario_admin")
                and request._obj_usuario_admin
            ):
                obj = request._obj_usuario_admin
                uo_id = obj.unidade_orcamentaria_id or None

            if not uo_id:
                kwargs["queryset"] = UnidadeAdministrativa.objects.none()
            else:
                kwargs["queryset"] = qs.filter(unidade_orcamentaria_id=uo_id)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):

        request._obj_usuario_admin = obj

        form = super().get_form(request, obj, **kwargs)
        if hasattr(form, "base_fields") and "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].required = True

        if (
            obj is None
            and hasattr(form, "base_fields")
            and "unidade_orcamentaria" in form.base_fields
        ):
            if request.user.unidade_orcamentaria_id:
                form.base_fields["unidade_orcamentaria"].initial = (
                    request.user.unidade_orcamentaria_id
                )

        if not request.user.is_superuser and "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].disabled = True

            if request.user.unidade_orcamentaria_id:
                form.base_fields["unidade_orcamentaria"].initial = (
                    request.user.unidade_orcamentaria_id
                )

        original_clean = form.clean

        def custom_clean(form_self):
            cleaned_data = original_clean(form_self)

            groups = cleaned_data.get("groups") or []
            uo = cleaned_data.get("unidade_orcamentaria")
            ua = cleaned_data.get("unidade_administrativa")

            from usuario.constants import (
                GRUPO_OPERADOR_INVENTARIO,
                GRUPO_GESTOR_PATRIMONIO,
            )
            from django.core.exceptions import ValidationError

            if not request.user.is_superuser and cleaned_data.get("is_superuser"):
                raise ValidationError(
                    {"is_superuser": "Você não tem permissão para definir super-admin."}
                )

            is_operador = any(g.name == GRUPO_OPERADOR_INVENTARIO for g in groups)
            is_gestor = any(g.name == GRUPO_GESTOR_PATRIMONIO for g in groups)

            if not uo:
                raise ValidationError(
                    {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
                )

            if not request.user.is_superuser:
                uo_criador = request.user.unidade_orcamentaria
                if not uo_criador:
                    raise ValidationError(
                        {
                            "unidade_orcamentaria": "Seu usuário não possui Unidade Orçamentária vinculada."
                        }
                    )
                cleaned_data["unidade_orcamentaria"] = uo_criador
                uo = uo_criador

            if ua and not uo:
                raise ValidationError(
                    {
                        "unidade_orcamentaria": "Selecione a Unidade Orçamentária antes de escolher a Unidade Administrativa."
                    }
                )

            if uo and ua and ua.unidade_orcamentaria_id != uo.id:

                cleaned_data["unidade_administrativa"] = None
                raise ValidationError(
                    {
                        "unidade_administrativa": "A Unidade Administrativa não pertence à Unidade Orçamentária selecionada. Selecione novamente."
                    }
                )

            if (
                is_operador
                and not is_gestor
                and not cleaned_data.get("unidade_administrativa")
            ):
                raise ValidationError(
                    {
                        "unidade_administrativa": "Operador de Inventário deve ter uma Unidade Administrativa vinculada."
                    }
                )

            return cleaned_data

        form.clean = custom_clean
        return form

    @admin.display(description="Grupo")
    def get_grupo(self, obj):
        if obj.is_gestor_patrimonio:
            return "GESTOR_PATRIMONIO"
        elif obj.is_operador_inventario:
            return "OPERADOR_INVENTARIO"
        return "-"


admin.site.register(Usuario, CustomUserModelAdmin)
