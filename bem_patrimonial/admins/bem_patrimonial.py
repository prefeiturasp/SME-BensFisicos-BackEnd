from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models import OuterRef, Subquery
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from bem_patrimonial.admins.actions.extracao_numeros import (
    aplicar_extracao_numero,
    simular_extracao_numero,
)
from bem_patrimonial.admins.filters.bem_patrimonial_filters import SemNumeroFilter
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

from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models.functions import Cast
from bem_patrimonial import constants
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa


@admin.action(description="Aprovar bens selecionados")
def aprovar_bens(_, request, queryset):
    if not request.user.is_gestor_patrimonio:
        messages.error(
            request,
            "Você não tem permissão para executar esta ação. Restrito ao grupo GESTOR_PATRIMONIO.",
        )
        return

    bens_aguardando = queryset.filter(status=constants.AGUARDANDO_APROVACAO)
    count_aguardando = bens_aguardando.count()
    count_outros = queryset.exclude(status=constants.AGUARDANDO_APROVACAO).count()

    if count_aguardando == 0:
        messages.warning(
            request,
            "Nenhum bem selecionado está com status 'Aguardando aprovação'.",
        )
        return

    try:
        with transaction.atomic():
            for bem in bens_aguardando:
                bem.status = constants.APROVADO
                bem.save(update_fields=["status", "atualizado_em"])

                StatusBemPatrimonial.objects.create(
                    bem_patrimonial=bem,
                    status=constants.APROVADO,
                    atualizado_por=request.user,
                    observacao="Aprovado em lote pelo gestor",
                )

        messages.success(
            request,
            f"{count_aguardando} bem(ns) aprovado(s) com sucesso.",
        )

        if count_outros > 0:
            messages.warning(
                request,
                f"{count_outros} bem(ns) não pôde(ram) ser aprovado(s) pois não estava(m) com status 'Aguardando aprovação'.",
            )

    except Exception as e:
        messages.error(
            request,
            f"Erro ao aprovar bens: {str(e)}",
        )


@admin.action(description="Reprovar bens selecionados")
def reprovar_bens(_, request, queryset):
    if not request.user.is_gestor_patrimonio:
        messages.error(
            request,
            "Você não tem permissão para executar esta ação. Restrito ao grupo GESTOR_PATRIMONIO.",
        )
        return

    bens_aguardando = queryset.filter(status=constants.AGUARDANDO_APROVACAO)
    count_aguardando = bens_aguardando.count()
    count_outros = queryset.exclude(status=constants.AGUARDANDO_APROVACAO).count()

    if count_aguardando == 0:
        messages.warning(
            request,
            "Nenhum bem selecionado está com status 'Aguardando aprovação'.",
        )
        return

    try:
        with transaction.atomic():
            for bem in bens_aguardando:
                bem.status = constants.NAO_APROVADO
                bem.save(update_fields=["status", "atualizado_em"])

                StatusBemPatrimonial.objects.create(
                    bem_patrimonial=bem,
                    status=constants.NAO_APROVADO,
                    atualizado_por=request.user,
                    observacao="Reprovado em lote pelo gestor",
                )

        messages.success(
            request,
            f"{count_aguardando} bem(ns) reprovado(s) com sucesso.",
        )

        if count_outros > 0:
            messages.warning(
                request,
                f"{count_outros} bem(ns) não pôde(ram) ser reprovado(s) pois não estava(m) com status 'Aguardando aprovação'.",
            )

    except Exception as e:
        messages.error(
            request,
            f"Erro ao reprovar bens: {str(e)}",
        )


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
    template = "admin/bem_patrimonial/edit_inline/tabular-historico.html"

    def has_view_or_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False


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
        "unidade_administrativa__codigo",
        "unidade_administrativa__nome", 
    )

    search_help_text = (
        "Pesquise por número patrimonial, nome, descrição, marca, modelo, "
        "localização, número de processo, código ou nome da Unidade Administrativa."
    )
    list_display_links = (
        "numero_patrimonial",
        "nome",
    )
    
    resource_class = BemPatrimonialResource

    list_filter = (
        "status",
        SemNumeroFilter,
        "numero_formato_antigo",
        ("criado_em", DateRangeFilter),
    )

    readonly_fields = (
        "status",
        "criado_por",
        "criado_em",
    )
    actions = [
        simular_extracao_numero,
        aplicar_extracao_numero,
        aprovar_bens,
        reprovar_bens,
    ]

    class Media:
        js = ("admin/bem_patrimonial.js",)
        css = {"all": ("admin/bem_patrimonial.css", "css/hide_crud_icons.css")}

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not request.user.is_gestor_patrimonio:
            actions.pop("aplicar_extracao_numero", None)
            actions.pop("aprovar_bens", None)
            actions.pop("reprovar_bens", None)
        return actions

    def get_list_display(self, request):
        if (
            request.user.is_operador_inventario
            and not request.user.is_gestor_patrimonio
        ):
            return ("numero_patrimonial", "nome", "status")
        return ("numero_patrimonial", "nome", "unidade_administrativa", "status")

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
            "numero_processo",
        ]
        if obj:
            base = [f for f in base if f != "cadastro_modo"]
        return base

    autocomplete_fields = ("unidade_administrativa",)
    ordering = ("-criado_em",)

    inlines = [HistoricoGeralInline]

    def get_form(self, request, obj=None, **kwargs):
        BaseForm = super().get_form(request, obj, **kwargs)

        if obj is None:
            original_clean = BaseForm.clean

            class CreateForm(BaseForm):
                def __init__(self_inner, *a, **kw):
                    super().__init__(*a, **kw)

                    modo = (getattr(self_inner, "data", None) or {}).get(
                        "cadastro_modo"
                    ) or (getattr(self_inner, "initial", {}) or {}).get("cadastro_modo")
                    if modo == "multi" and "localizacao" in self_inner.fields:
                        self_inner.fields["localizacao"].required = False

                    if "unidade_administrativa" in self_inner.fields:
                        fld = self_inner.fields["unidade_administrativa"]
                        fld.required = True
                        ua_user = getattr(request.user, "unidade_administrativa", None)

                        if ua_user:
                            fld.queryset = UnidadeAdministrativa.objects.filter(
                                pk=ua_user.pk, status=UnidadeAdministrativa.ATIVA
                            )
                            fld.initial = ua_user
                            fld.disabled = True
                        else:
                            fld.queryset = UnidadeAdministrativa.objects.filter(
                                status=UnidadeAdministrativa.ATIVA
                            )

                def clean(self_inner):
                    cleaned_data = original_clean(self_inner)
                    ua_user = getattr(request.user, "unidade_administrativa", None)
                    ua_form = cleaned_data.get("unidade_administrativa")

                    if (
                        not ua_form
                        and ua_user
                        and request.user.is_operador_inventario
                        and not request.user.is_gestor_patrimonio
                    ):
                        cleaned_data["unidade_administrativa"] = ua_user
                        ua_form = ua_user

                    if not ua_form:
                        raise ValidationError(
                            {
                                "unidade_administrativa": "Selecione a Unidade Administrativa."
                            }
                        )

                    if ua_user and not ua_user.is_ativa:
                        raise ValidationError(
                            f"Não é possível criar bens patrimoniais. Sua unidade administrativa "
                            f"'{ua_user.nome}' está inativa. Entre em contato com o gestor de patrimônio."
                        )

                    if ua_user and ua_form != ua_user:
                        raise ValidationError(
                            {
                                "unidade_administrativa": "Você só pode criar bens na Unidade Administrativa vinculada ao seu usuário."
                            }
                        )

                    return cleaned_data

            return CreateForm

        class EditForm(BaseForm):
            def __init__(self_inner, *a, **kw):
                super().__init__(*a, **kw)
                if "unidade_administrativa" in self_inner.fields:
                    self_inner.fields["unidade_administrativa"].disabled = True
                    self_inner.fields["unidade_administrativa"].required = True

            def clean(self_inner):
                cleaned = super().clean()
                if self_inner.instance and self_inner.instance.pk:
                    ua_original = self_inner.instance.unidade_administrativa
                    ua_post = cleaned.get("unidade_administrativa") or ua_original
                    if ua_post != ua_original:
                        raise ValidationError(
                            {
                                "unidade_administrativa": "Não é permitido alterar a Unidade Administrativa na edição."
                            }
                        )
                    if not ua_post:
                        raise ValidationError(
                            {
                                "unidade_administrativa": "Unidade Administrativa é obrigatória."
                            }
                        )
                return cleaned

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
        qs = (
            super()
            .get_queryset(request)
            .select_related("unidade_administrativa", "criado_por")
        )

        user = request.user
        ua_user = getattr(user, "unidade_administrativa", None)

        if user.is_gestor_patrimonio and not ua_user:
            pass
        elif ua_user:
            qs = qs.filter(unidade_administrativa=ua_user)
        else:
            qs = qs.none()

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
        user = request.user
        ua_user = getattr(user, "unidade_administrativa", None)

        if user.is_gestor_patrimonio and not ua_user:
            pass
        elif ua_user:
            queryset = queryset.filter(unidade_administrativa=ua_user)
        else:
            queryset = queryset.none()

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

            post["cadastro_modo"] = "multi"

            post["sem_numeracao"] = "on"
            post["numero_patrimonial"] = ""
            post["numero_formato_antigo"] = ""

            form_cls = self.get_form(request)
            form = form_cls(post, request.FILES)

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
                    except Exception as ex:
                        errors.append(f"Linha {idx}: Erro inesperado: {str(ex)}")

                if errors:
                    transaction.set_rollback(True)

            if errors:

                for e in errors:
                    messages.error(request, e)
                form.add_error(
                    None,
                    "Não foi possível concluir o cadastro em lote. Corrija as linhas com erro e tente novamente.",
                )
                return super().add_view(request, form_url, extra_context)

            messages.success(request, f"{len(criados)} bens criados com sucesso.")
            changelist_url = reverse(
                f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
            )
            return HttpResponseRedirect(changelist_url)

        return super().add_view(request, form_url, extra_context)

    def render_change_form(self, request, context, *args, **kwargs):
        """
        Renderiza o formulário e injeta o bloco do modo múltiplo em um ponto seguro,
        mesmo sem o campo 'foto' no layout.
        """
        response = super().render_change_form(request, context, *args, **kwargs)

        server_payload = request.POST.get("multi_payload") or "[]"
        is_multi_by_radio = request.POST.get("cadastro_modo") == "multi"
        has_rows_payload = bool(
            server_payload.strip()
        ) and server_payload.strip() not in ("[]", "")
        force_multi = "1" if (is_multi_by_radio or has_rows_payload) else "0"

        from django.utils.safestring import mark_safe

        anchor = format_html(
            '<div id="multi-inline-root" data-force-multi="{}"></div>'
            '<script id="multi-inline-data" type="application/json">{}</script>',
            force_multi,
            mark_safe(server_payload),
        )

        try:
            html = response.rendered_content
            if "</div><!-- END form-container -->" in html:
                html = html.replace(
                    "</div><!-- END form-container -->",
                    anchor + "</div><!-- END form-container -->",
                )
            elif "</form>" in html:
                html = html.replace("</form>", anchor + "</form>")
            response.content = html.encode(response.charset)
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

    def get_search_results(self, request, queryset, search_term):
        qs, use_distinct = super().get_search_results(request, queryset, search_term)

        if request.path.endswith("/autocomplete/"):
            app_label = request.GET.get("app_label")
            model_name = request.GET.get("model_name")
            field_name = request.GET.get("field_name")

            if (
                app_label == "bem_patrimonial"
                and model_name in ("movimentacaobensitem", "baixafisicabensitem")
                and field_name == "bem"
            ):
                ua_origem = request.GET.get("ua_origem")
                if not ua_origem:
                    return qs.none(), use_distinct
                qs = (
                    qs.filter(status=constants.APROVADO)
                    .filter(unidade_administrativa_id=ua_origem)
                )

                exclude_bens = request.GET.get("exclude_bens")
                if exclude_bens:
                    ids = [int(pk) for pk in exclude_bens.split(",") if pk.isdigit()]
                    if ids:
                        qs = qs.exclude(pk__in=ids)

        return qs, use_distinct
