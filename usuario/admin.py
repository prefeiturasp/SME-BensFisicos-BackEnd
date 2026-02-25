from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django_admin_listfilter_dropdown.filters import DropdownFilter
from rangefilter.filters import DateRangeFilter
from usuario.models import Usuario
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


class GroupSingleSelectWidget(forms.Select):

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        return [value] if value else []


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
    filter_horizontal = ("unidades_administrativas",)

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
                    "unidades_administrativas",
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
                    "unidades_administrativas",
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

    def _resolver_uo_id_contexto_admin(self, request):
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
            uo_id = request._obj_usuario_admin.unidade_orcamentaria_id or None

        if not uo_id and not request.user.is_superuser:
            uo_id = request.user.unidade_orcamentaria_id or None

        if not uo_id and request.user.is_superuser:
            uo_id = (
                UnidadeAdministrativa.objects.filter(status=UnidadeAdministrativa.ATIVA)
                .order_by("unidade_orcamentaria__codigo", "codigo", "id")
                .values_list("unidade_orcamentaria_id", flat=True)
                .first()
            )

            if not uo_id:
                uo_id = (
                    UnidadeOrcamentaria.objects.order_by("codigo", "id")
                    .values_list("id", flat=True)
                    .first()
                )

        return uo_id

    def _get_grupo_queryset(self):
        return Group.objects.filter(
            name__in=[GRUPO_GESTOR_PATRIMONIO, GRUPO_OPERADOR_INVENTARIO]
        ).order_by("name")

    def _grupo_preferencial(self, user):
        nomes = set(user.groups.values_list("name", flat=True))
        if GRUPO_GESTOR_PATRIMONIO in nomes:
            return (
                self._get_grupo_queryset().filter(name=GRUPO_GESTOR_PATRIMONIO).first()
            )
        if GRUPO_OPERADOR_INVENTARIO in nomes:
            return (
                self._get_grupo_queryset()
                .filter(name=GRUPO_OPERADOR_INVENTARIO)
                .first()
            )
        return None

    def _selecionar_grupo_unico(self, groups_qs):
        if not groups_qs:
            return None

        nomes = set(groups_qs.values_list("name", flat=True))
        if GRUPO_GESTOR_PATRIMONIO in nomes:
            return groups_qs.filter(name=GRUPO_GESTOR_PATRIMONIO).first()
        if GRUPO_OPERADOR_INVENTARIO in nomes:
            return groups_qs.filter(name=GRUPO_OPERADOR_INVENTARIO).first()
        return groups_qs.first()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "groups":
            kwargs["queryset"] = self._get_grupo_queryset()
            kwargs["widget"] = forms.Select

        if db_field.name == "unidades_administrativas":
            qs = UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            )
            uo_id = self._resolver_uo_id_contexto_admin(request)

            if uo_id:
                kwargs["queryset"] = qs.filter(unidade_orcamentaria_id=uo_id)
            else:
                kwargs["queryset"] = UnidadeAdministrativa.objects.none()
        return super().formfield_for_manytomany(db_field, request, **kwargs)

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
            uo_id = self._resolver_uo_id_contexto_admin(request)

            if not uo_id:
                kwargs["queryset"] = UnidadeAdministrativa.objects.none()
            else:
                kwargs["queryset"] = qs.filter(unidade_orcamentaria_id=uo_id)

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_form(self, request, obj=None, **kwargs):

        request._obj_usuario_admin = obj

        form = super().get_form(request, obj, **kwargs)

        if hasattr(form, "base_fields"):
            if "groups" in form.base_fields:
                form.base_fields["groups"].queryset = self._get_grupo_queryset()
                form.base_fields["groups"].label = "Grupo"
                form.base_fields["groups"].required = False
                form.base_fields["groups"].widget = GroupSingleSelectWidget()
                if obj and obj.pk:
                    grupo_inicial = self._grupo_preferencial(obj)
                    if grupo_inicial:
                        form.base_fields["groups"].initial = [grupo_inicial.pk]
        if hasattr(form, "base_fields") and "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].required = True

        if (
            obj is None
            and hasattr(form, "base_fields")
            and "unidade_orcamentaria" in form.base_fields
        ):
            initial_uo_id = self._resolver_uo_id_contexto_admin(request)
            if initial_uo_id:
                form.base_fields["unidade_orcamentaria"].initial = initial_uo_id

        if not request.user.is_superuser and "unidade_orcamentaria" in form.base_fields:
            form.base_fields["unidade_orcamentaria"].disabled = True

            if request.user.unidade_orcamentaria_id:
                form.base_fields["unidade_orcamentaria"].initial = (
                    request.user.unidade_orcamentaria_id
                )

        original_clean = form.clean

        def custom_clean(form_self):
            cleaned_data = original_clean(form_self)

            groups_qs = cleaned_data.get("groups")
            grupo = self._selecionar_grupo_unico(groups_qs)
            uo = cleaned_data.get("unidade_orcamentaria")
            ua = cleaned_data.get("unidade_administrativa")
            from django.core.exceptions import ValidationError

            if not request.user.is_superuser and cleaned_data.get("is_superuser"):
                raise ValidationError(
                    {"is_superuser": "Você não tem permissão para definir super-admin."}
                )

            is_operador = bool(grupo and grupo.name == GRUPO_OPERADOR_INVENTARIO)
            is_gestor = bool(grupo and grupo.name == GRUPO_GESTOR_PATRIMONIO)

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
                        "unidade_orcamentaria": "Selecione a Unidade Orçamentária antes de escolher a Unidade Administrativa."  # noqa: E501
                    }
                )

            if uo and ua and ua.unidade_orcamentaria_id != uo.id:

                cleaned_data["unidade_administrativa"] = None
                raise ValidationError(
                    {
                        "unidade_administrativa": "A Unidade Administrativa não pertence à Unidade Orçamentária selecionada. Selecione novamente."  # noqa: E501
                    }
                )

            if (
                is_operador
                and not is_gestor
                and not cleaned_data.get("unidade_administrativa")
            ):
                raise ValidationError(
                    {
                        "unidade_administrativa": "Operador de Inventário deve ter uma Unidade Administrativa vinculada."  # noqa: E501
                    }
                )

            uas_m2m_ids = cleaned_data.get("unidades_administrativas", [])

            if is_operador and not is_gestor:
                if not uas_m2m_ids:
                    raise ValidationError(
                        {
                            "unidades_administrativas": "Operador deve ter pelo menos uma UA."
                        }
                    )
                if uo:
                    uas_invalidas = [
                        u for u in uas_m2m_ids if u.unidade_orcamentaria_id != uo.id
                    ]
                    if uas_invalidas:
                        raise ValidationError(
                            {
                                "unidades_administrativas": "Todas as UAs devem pertencer à UO selecionada."
                            }
                        )
                if ua and ua not in uas_m2m_ids:
                    raise ValidationError(
                        {
                            "unidade_administrativa": "A UA ativa deve estar entre as UAs selecionadas."
                        }
                    )

            return cleaned_data

        form.clean = custom_clean
        return form

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance

        grupo = self._selecionar_grupo_unico(form.cleaned_data.get("groups"))
        if grupo:
            obj.groups.set([grupo])
        else:
            obj.groups.clear()

        if obj.is_operador_inventario and not obj.unidade_administrativa_id:
            primeira = obj.unidades_administrativas.first()
            if primeira:
                obj.unidade_administrativa = primeira
                obj.save(update_fields=["unidade_administrativa"])

    @admin.display(description="Grupo")
    def get_grupo(self, obj):
        if obj.is_gestor_patrimonio:
            return "GESTOR_PATRIMONIO"
        elif obj.is_operador_inventario:
            return "OPERADOR_INVENTARIO"
        return "-"


admin.site.register(Usuario, CustomUserModelAdmin)
