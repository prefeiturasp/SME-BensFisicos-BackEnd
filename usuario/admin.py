from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group
from django_admin_listfilter_dropdown.filters import DropdownFilter
from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import XLSX
from rangefilter.filters import DateRangeFilter
from usuario.models import Usuario
from usuario.resources import UsuarioResource
from dados_comuns.models import UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.escopo import filtrar_queryset_usuario_por_escopo
from django.core.exceptions import ValidationError

from usuario.constants import GRUPO_OPERADOR_INVENTARIO, GRUPO_GESTOR_PATRIMONIO


def _ensure_uo_obrigatoria(uo):
    if not uo:
        raise ValidationError(
            {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
        )


def _apply_usuario_clean_validation(*, form_ref, admin, cleaned_data):
    """Aplica as validações de clean do formulário de usuário (extraído para reduzir complexidade)."""
    groups_qs = cleaned_data.get("groups")
    grupo = admin._selecionar_grupo_unico(groups_qs)
    uo = cleaned_data.get("unidade_orcamentaria")
    ua = cleaned_data.get("unidade_administrativa")

    if not form_ref.user.is_superuser and cleaned_data.get("is_superuser"):
        raise ValidationError(
            {"is_superuser": "Você não tem permissão para definir super-admin."}
        )

    is_operador = bool(grupo and grupo.name == GRUPO_OPERADOR_INVENTARIO)
    is_gestor = bool(grupo and grupo.name == GRUPO_GESTOR_PATRIMONIO)

    _ensure_uo_obrigatoria(uo)

    if not form_ref.user.is_superuser:
        uo_criador = form_ref.user.unidade_orcamentaria
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
        _validate_operador_uas(uo, ua, uas_m2m_ids)


def _validate_operador_uas(uo, ua, uas_m2m_ids):
    """Valida regras de UAs para operador de inventário."""
    if not uas_m2m_ids:
        raise ValidationError(
            {"unidades_administrativas": "Operador deve ter pelo menos uma UA."}
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


class GroupSingleSelectWidget(forms.Select):

    def value_from_datadict(self, data, files, name):
        value = super().value_from_datadict(data, files, name)
        return [value] if value else []

    def optgroups(self, name, value, attrs=None):
        groups = super().optgroups(name, value, attrs)
        value = value or []

        has_blank = any(
            option["value"] in ("", None)
            for _, subgroup, _ in groups
            for option in subgroup
        )
        if not has_blank:
            empty_option = self.create_option(
                name,
                "",
                "---------",
                selected=not bool(value),
                index=0,
                subindex=None,
                attrs=attrs,
            )
            groups = [(None, [empty_option], 0)] + groups

        return groups


class CustomUserModelAdmin(ImportExportModelAdmin, UserAdmin):
    model = Usuario
    resource_class = UsuarioResource
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

    def has_import_permission(self, request):
        return False

    def has_export_permission(self, request):
        return request.user.is_superuser or request.user.is_gestor_patrimonio

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_module_permission(self, request):
        return self._pode_gerenciar(request.user)

    def has_view_permission(self, request, obj=None):
        return self._pode_gerenciar(request.user)

    def has_add_permission(self, request):
        return self._pode_gerenciar(request.user)

    def has_change_permission(self, request, obj=None):
        return self._pode_gerenciar(request.user)

    def has_delete_permission(self, request, obj=None):
        return False

    def _get_queryset_filtrado_por_escopo(self, request):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related("unidades_administrativas")
        return filtrar_queryset_usuario_por_escopo(request.user, qs)

    def get_queryset(self, request):
        return self._get_queryset_filtrado_por_escopo(request)

    def get_export_queryset(self, request):
        return self.get_queryset(request)

    def get_export_formats(self):
        return [XLSX]

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
        if isinstance(groups_qs, Group):
            return groups_qs

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
            self._configure_uo_queryset(request, kwargs)
        if db_field.name == "unidade_administrativa":
            self._configure_ua_queryset(request, kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _configure_uo_queryset(self, request, kwargs):
        if not request.user.is_superuser:
            if request.user.unidade_orcamentaria_id:
                kwargs["queryset"] = UnidadeOrcamentaria.objects.filter(
                    pk=request.user.unidade_orcamentaria_id
                )
            else:
                kwargs["queryset"] = UnidadeOrcamentaria.objects.none()
        else:
            kwargs["queryset"] = UnidadeOrcamentaria.objects.all()

    def _configure_ua_queryset(self, request, kwargs):
        qs = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        )
        uo_id = self._resolver_uo_id_contexto_admin(request)
        if not uo_id:
            kwargs["queryset"] = UnidadeAdministrativa.objects.none()
        else:
            kwargs["queryset"] = qs.filter(unidade_orcamentaria_id=uo_id)

    def get_form(self, request, obj=None, **kwargs):
        request._obj_usuario_admin = obj
        form = super().get_form(request, obj, **kwargs)
        self._configure_groups_field(form, obj)
        self._configure_uo_field(form, request, obj)
        self._wrap_form_clean_with_validation(form, request)
        return form

    def _configure_groups_field(self, form, obj):
        if not (hasattr(form, "base_fields") and "groups" in form.base_fields):
            return
        form.base_fields["groups"] = forms.ModelMultipleChoiceField(
            queryset=self._get_grupo_queryset(),
            required=False,
            label="Grupo",
            widget=GroupSingleSelectWidget,
        )
        if obj and obj.pk:
            grupo_inicial = self._grupo_preferencial(obj)
            form.base_fields["groups"].initial = (
                [grupo_inicial.pk] if grupo_inicial else []
            )
        else:
            form.base_fields["groups"].initial = []

    def _configure_uo_field(self, form, request, obj):
        if not (hasattr(form, "base_fields") and "unidade_orcamentaria" in form.base_fields):
            return
        form.base_fields["unidade_orcamentaria"].required = True
        if obj is None and request.user.unidade_orcamentaria_id:
            initial_uo_id = self._resolver_uo_id_contexto_admin(request)
            if initial_uo_id:
                form.base_fields["unidade_orcamentaria"].initial = initial_uo_id
        if not request.user.is_superuser:
            form.base_fields["unidade_orcamentaria"].disabled = True
            if request.user.unidade_orcamentaria_id:
                form.base_fields["unidade_orcamentaria"].initial = (
                    request.user.unidade_orcamentaria_id
                )

    def _wrap_form_clean_with_validation(self, form, request):
        original_clean = form.clean
        request_ref = request

        def custom_clean(form_self):
            cleaned_data = original_clean(form_self)
            _apply_usuario_clean_validation(
                form_ref=request_ref, admin=self, cleaned_data=cleaned_data
            )
            return cleaned_data

        form.clean = custom_clean

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance

        if request.method == "POST" and "groups" in request.POST:
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
