from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models
from django.db.models import OuterRef, Subquery
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from bem_patrimonial.admins.forms.bem_patrimonial_form import BemPatrimonialAdminForm
from bem_patrimonial.models import (
    BemPatrimonial,
    StatusBemPatrimonial,
)
from bem_patrimonial.formats import PDFFormat
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from rangefilter.filters import DateRangeFilter
from import_export.formats.base_formats import CSV, XLS, XLSX, HTML
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from dados_comuns.models import HistoricoGeral
from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models.functions import Cast
from bem_patrimonial import constants


class StatusBemPatrimonialInline(admin.TabularInline):
    model = StatusBemPatrimonial
    extra = 0
    readonly_fields = ("atualizado_por", "atualizado_em")


class HistoricoGeralInline(GenericTabularInline):
    model = HistoricoGeral
    extra = 0
    can_delete = False
    readonly_fields = (
        "campo",
        "valor_antigo",
        "valor_novo",
        "alterado_por",
        "alterado_em",
    )
    fields = ("campo", "valor_antigo", "valor_novo", "alterado_por", "alterado_em")
    ordering = ("-alterado_em",)

    def has_view_or_change_permission(self, request, obj=None):
        return True


class BemPatrimonialResource(resources.ModelResource):
    class Meta:
        model = BemPatrimonial
        fields = (
            "id",
            "status",
            "nome",
            "marca",
            "modelo",
            "descricao",
            "valor_unitario",
            "numero_processo",
            "numero_patrimonial",
            "localizacao",
            "criado_por__nome",
            "criado_em",
        )
        export_order = fields


class BemPatrimonialAdmin(ImportExportModelAdmin):
    model = BemPatrimonial
    form = BemPatrimonialAdminForm

    list_display = (
        "numero_patrimonial",
        "nome",
        "unidade_administrativa",
        "status",
    )
    search_fields = (
        "numero_patrimonial",
        "nome",
        "descricao",
        "marca",
        "modelo",
        "localizacao",
        "numero_processo",
    )
    list_display_links = ("thumb", "numero_patrimonial", "nome")
    search_help_text = "Pesquise por número patrimonial, nome, descrição, marca, modelo, localização ou número de processo."
    resource_class = BemPatrimonialResource

    list_filter = (
        "status",
        "sem_numeracao",
        "numero_formato_antigo",
        ("criado_em", DateRangeFilter),
    )

    readonly_fields = (
        "status",
        "criado_por",
        "criado_em",
        "foto_preview",
    )

    class Media:
        js = ("admin/bem_patrimonial.js",)
        css = {"all": ("admin/bem_patrimonial.css",)}

    def get_list_display(self, request):
        if getattr(request.user, "is_operador_inventario", False):
            return ("thumb", "numero_patrimonial", "nome", "status")
        return (
            "thumb",
            "numero_patrimonial",
            "nome",
            "unidade_administrativa",
            "status",
        )

    def get_fields(self, request, obj=None):
        base = [
            "cadastro_modo",
            "status",
            "unidade_administrativa",
            ("numero_patrimonial", "numero_formato_antigo", "sem_numeracao"),
            "nome",
            "descricao",
            ("valor_unitario", "marca", "modelo"),
            ("localizacao"),
            "foto_preview",
            ("foto", "numero_processo"),
        ]
        if obj:
            base = [f for f in base if f != "cadastro_modo"]
        return base

    autocomplete_fields = ("unidade_administrativa",)
    ordering = ("-criado_em",)

    inlines = [StatusBemPatrimonialInline, HistoricoGeralInline]

    def get_form(self, request, obj=None, **kwargs):
        BaseForm = super().get_form(request, obj, **kwargs)

        # Regras na CRIAÇÃO (mantém sua validação atual)
        if obj is None:
            original_clean = BaseForm.clean

            class CreateForm(BaseForm):
                def clean(self_inner):
                    cleaned_data = original_clean(self_inner)
                    ua = getattr(request.user, "unidade_administrativa", None)
                    if ua and not ua.is_ativa:
                        raise ValidationError(
                            f"Não é possível criar bens patrimoniais. Sua unidade administrativa "
                            f"'{ua.nome}' está inativa. Entre em contato com o gestor de patrimônio."
                        )
                    return cleaned_data

            return CreateForm

        class EditForm(BaseForm):
            def __init__(self_inner, *a, **kw):
                super().__init__(*a, **kw)
                inst = getattr(self_inner, "instance", None)
                if inst and getattr(inst, "sem_numeracao", False):
                    for fname in (
                        "numero_patrimonial",
                        "numero_formato_antigo",
                        "sem_numeracao",
                    ):
                        if fname in self_inner.fields:
                            self_inner.fields[fname].disabled = True

        return EditForm

    def save_model(self, request, obj, form, change):
        if obj.id is None:
            obj.criado_por = request.user
            if not obj.status:
                obj.status = constants.AGUARDANDO_APROVACAO
        try:
            super().save_model(request, obj, form, change)
        except IntegrityError as e:
            if "numero_patrimonial" in str(e).lower():
                form.add_error(
                    "numero_patrimonial",
                    "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema.",
                )
                raise ValidationError(
                    {
                        "numero_patrimonial": "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema."
                    }
                )
            raise

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        qs = qs.select_related("unidade_administrativa", "criado_por")

        if getattr(request.user, "is_operador_inventario", False) and not getattr(
            request.user, "is_gestor_patrimonio", True
        ):
            qs = qs.filter(unidade_administrativa=request.user.unidade_administrativa)

        ct = ContentType.objects.get_for_model(BemPatrimonial)
        pk_as_char = Cast(OuterRef("pk"), output_field=models.CharField())

        hist_qs = HistoricoGeral.objects.filter(
            content_type=ct, object_id=pk_as_char
        ).order_by("-alterado_em")

        qs = qs.annotate(
            audit_last_at=Subquery(hist_qs.values("alterado_em")[:1]),
            audit_last_by_id=Subquery(hist_qs.values("alterado_por_id")[:1]),
        )
        return qs

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)

        if getattr(request.user, "is_operador_inventario", False) and not getattr(
            request.user, "is_gestor_patrimonio", True
        ):
            queryset = queryset.filter(
                unidade_administrativa=request.user.unidade_administrativa
            )

        return queryset

    def get_export_formats(self):
        return [CSV, XLSX, XLS, HTML, PDFFormat]

    def get_resource_kwargs(self, request, **kwargs):
        rk = super().get_resource_kwargs(request, **kwargs)
        rk["request"] = request
        return rk

    def get_export_data(self, file_format, queryset, *args, **kwargs):
        if isinstance(file_format, PDFFormat):
            request = kwargs.get("request")
            file_format._export_request = request
            file_format._export_queryset = queryset
        return super().get_export_data(file_format, queryset, *args, **kwargs)

    def save_formset(self, request, form, formset, change):
        if formset.model is StatusBemPatrimonial:
            self.save_status(request, form, formset, change)
        formset.save()

    def save_status(self, request, form, formset, change):
        instances = formset.save(commit=False)
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            instance.atualizado_por = request.user
            instance.save()
        formset.save_m2m()

    def add_view(self, request, form_url="", extra_context=None):
        """
        Intercepta o POST no modo 'multi':
        - valida form base (campos comuns) sem esbarrar na regra do numero_patrimonial;
        - valida payload das linhas;
        - cria N bens.
        """
        if request.method == "POST" and request.POST.get("cadastro_modo") == "multi":

            post = request.POST.copy()

            post["sem_numeracao"] = "on"
            post["numero_patrimonial"] = ""
            post["numero_formato_antigo"] = ""

            form = self.get_form(request)(post, request.FILES)

            if not form.is_valid():

                return super().add_view(request, form_url, extra_context)

            import json

            raw = request.POST.get("multi_payload") or "[]"
            try:
                linhas = json.loads(raw)
            except Exception:
                linhas = []

            if not linhas:
                form.add_error(
                    None, "Adicione ao menos uma linha no modo Múltiplos Bens."
                )
                return super().add_view(request, form_url, extra_context)

            base = {
                "status": form.cleaned_data.get("status")
                or constants.AGUARDANDO_APROVACAO,
                "unidade_administrativa": form.cleaned_data.get(
                    "unidade_administrativa"
                ),
                "nome": form.cleaned_data.get("nome"),
                "descricao": form.cleaned_data.get("descricao"),
                "valor_unitario": form.cleaned_data.get("valor_unitario"),
                "marca": form.cleaned_data.get("marca"),
                "modelo": form.cleaned_data.get("modelo"),
                "numero_processo": form.cleaned_data.get("numero_processo"),
                "foto": form.cleaned_data.get("foto"),
            }

            if base["status"] in (None, ""):
                try:
                    base["status"] = BemPatrimonial._meta.get_field(
                        "status"
                    ).get_default()
                except Exception:
                    fld = BemPatrimonial._meta.get_field("status")
                    if getattr(fld, "choices", None):
                        base["status"] = fld.choices[0][0]

            criados, errors = [], []

            from django.db import transaction, IntegrityError
            from django.core.exceptions import ValidationError

            with transaction.atomic():
                for idx, row in enumerate(linhas, start=1):

                    def to_bool(v):
                        if isinstance(v, bool):
                            return v
                        if v is None:
                            return False
                        return str(v).strip().lower() in (
                            "1",
                            "true",
                            "on",
                            "yes",
                            "y",
                            "t",
                        )

                    numero_patrimonial_raw = (
                        row.get("numero_patrimonial") or ""
                    ).strip()
                    numero_formato_antigo = to_bool(row.get("numero_formato_antigo"))
                    sem_numeracao = to_bool(row.get("sem_numeracao"))
                    localizacao = (row.get("localizacao") or "").strip() or None
                    if not localizacao:
                        errors.append(
                            f"Linha {idx}: Informe a Localização (obrigatória)."
                        )
                        continue

                    numero_patrimonial = numero_patrimonial_raw or None
                    if sem_numeracao:
                        numero_patrimonial = None

                    bem = BemPatrimonial(
                        criado_por=request.user,
                        numero_patrimonial=numero_patrimonial,
                        numero_formato_antigo=numero_formato_antigo,
                        sem_numeracao=sem_numeracao,
                        localizacao=localizacao,
                        **base,
                    )

                    try:
                        bem.full_clean()
                        bem.save()
                        criados.append(bem)
                    except ValidationError as ve:
                        err_msgs = (
                            "; ".join(
                                [
                                    f"{k}: {', '.join(v)}"
                                    for k, v in ve.message_dict.items()
                                ]
                            )
                            if hasattr(ve, "message_dict")
                            else str(ve)
                        )
                        errors.append(f"Linha {idx}: {err_msgs}")
                    except IntegrityError as ie:
                        errors.append(f"Linha {idx}: {str(ie)}")

                if errors:
                    transaction.set_rollback(True)

            if errors:
                for e in errors:
                    messages.error(request, e)

                return super().add_view(request, form_url, extra_context)

            messages.success(request, f"{len(criados)} bens criados com sucesso.")
            changelist_url = reverse(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
            )
            return HttpResponseRedirect(changelist_url)

        return super().add_view(request, form_url, extra_context)

    def render_change_form(self, request, context, *args, **kwargs):
        response = super().render_change_form(request, context, *args, **kwargs)

        # Reaproveita sua lógica atual apenas para calcular flags/dados
        server_payload = request.POST.get("multi_payload") or "[]"
        is_multi_by_radio = request.POST.get("cadastro_modo") == "multi"
        has_rows_payload = bool(
            server_payload.strip()
        ) and server_payload.strip() not in ("[]", "")
        force_multi = "1" if (is_multi_by_radio or has_rows_payload) else "0"

        # Escapar para atributo HTML
        server_payload_attr = (
            server_payload.replace("\\", "\\\\")
            .replace('"', "&quot;")
            .replace("\n", "")
            .replace("\r", "")
        )

        from django.utils.safestring import mark_safe

        anchor = format_html(
            '<div id="multi-inline-root" data-force-multi="{}"></div>'
            '<script id="multi-inline-data" type="application/json">{}</script>',
            force_multi,
            mark_safe(server_payload),  # já é JSON vindo do POST
        )

        try:
            response.content = response.rendered_content.replace(
                "</form>", anchor + "</form>"
            ).encode(response.charset)
        except Exception:
            pass
        return response

    def alterado_em_ultimo(self, obj):
        return getattr(obj, "audit_last_at", None)

    alterado_em_ultimo.short_description = "Última alteração"
    alterado_em_ultimo.admin_order_field = "audit_last_at"

    def alterado_por_ultimo(self, obj):
        user_id = getattr(obj, "audit_last_by_id", None)
        if not user_id:
            return "—"
        User = get_user_model()
        try:
            u = User.objects.only("first_name", "last_name", "username").get(id=user_id)
            return u.get_full_name() or u.username
        except User.DoesNotExist:
            return "—"

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    alterado_por_ultimo.short_description = "Alterado por"

    @admin.display(description="Foto")
    def thumb(self, obj):
        if getattr(obj, "foto", None) and hasattr(obj.foto, "url") and obj.foto.url:
            return format_html(
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;" />',
                obj.foto.url,
            )
        return "—"

    @admin.display(description="Pré-visualização")
    def foto_preview(self, obj):
        try:
            if (
                obj
                and obj.pk
                and getattr(obj, "foto", None)
                and hasattr(obj.foto, "url")
                and obj.foto.url
            ):
                return format_html(
                    '<a href="{}" target="_blank" rel="noopener">'
                    '<img src="{}" style="max-height:200px;border-radius:8px;border:1px solid #e5e7eb;padding:4px;background:#fff;" />'
                    "</a>",
                    obj.foto.url,
                    obj.foto.url,
                )
        except Exception:
            pass
        return "—"
