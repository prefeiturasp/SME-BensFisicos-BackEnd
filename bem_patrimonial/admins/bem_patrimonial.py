from django.contrib import admin, messages
from django.core.exceptions import ValidationError, PermissionDenied
from django.db import IntegrityError, models, transaction
from django.db.models import OuterRef, Subquery
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.utils import timezone
from django.template.response import TemplateResponse
import re

from bem_patrimonial.admins.actions.extracao_numeros import (
    aplicar_extracao_numero,
    simular_extracao_numero,
)
from bem_patrimonial.admins.filters.bem_patrimonial_filters import SemNumeroFilter
from bem_patrimonial.admins.forms.bem_patrimonial_form import BemPatrimonialAdminForm
from bem_patrimonial.models import (
    BaixaFisicaBensItem,
    BemPatrimonial,
    StatusBemPatrimonial,
)
from bem_patrimonial.formats import PDFFormat
from import_export.admin import ImportExportModelAdmin
from import_export import resources
from import_export.widgets import DecimalWidget
from rangefilter.filters import DateRangeFilter
from import_export.formats.base_formats import CSV, XLS, XLSX, HTML
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model

from django.contrib.contenttypes.admin import GenericTabularInline
from django.db.models.functions import Cast, Concat
from bem_patrimonial import constants
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa
from bem_patrimonial.admins.filters.baixados_periodo_filter import (
    BaixadosMaisDeUmPeriodoFilter,
    BuscaGeralTodasUOsFilter,
    StatusBemPatrimonialFilter,
)
from dados_comuns.escopo import (
    filtrar_queryset_bem_por_escopo_com_transferencia,
    filtrar_queryset_por_escopo,
    filtrar_ua_origem_por_escopo,
    validar_objeto_no_escopo,
    obter_unidade_orcamentaria_id_do_usuario,
    usuario_e_super_admin,
)

HTML_END_FORM_CONTAINER = "</div><!-- END form-container -->"
HTML_END_FORM = "</form>"


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
                f"{count_outros} bem(ns) não pôde(ram) ser aprovado(s) pois não estava(m) com status 'Aguardando aprovação'.",  # noqa E501
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
                f"{count_outros} bem(ns) não pôde(ram) ser reprovado(s) pois não estava(m) com status 'Aguardando aprovação'.",  # noqa E501
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
        "justificativa",
        "alterado_por",
        "alterado_em",
    )
    fields = (
        "campo",
        "valor_antigo",
        "valor_novo",
        "justificativa",
        "alterado_por",
        "alterado_em",
    )
    ordering = ("-alterado_em",)
    template = "admin/bem_patrimonial/edit_inline/tabular-historico.html"

    def has_view_or_change_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False


# ---------------------------------------------------------------------------
# Colunas aceitas na planilha de importação (Ponto 1)
# ---------------------------------------------------------------------------

COLUNAS_MODELO = (
    "numero_patrimonial",
    "nome",
    "descricao",
    "valor_unitario",
    "marca",
    "modelo",
)


class BemPatrimonialResource(resources.ModelResource):
    """
    Resource usado pelo django-import-export no Django Admin.

    Comportamento aplicado na importação:
    - Aceita apenas planilhas com exatamente as 6 colunas do modelo.
    - Valida o arquivo INTEIRO antes de salvar qualquer bem (tudo ou nada).
    - Se houver qualquer erro, rejeita toda a carga sem salvar nada.
    - Todos os bens importados entram com status Aguardando Aprovação.
    - A Unidade Administrativa usada é sempre a do usuário logado.
    - marca e modelo em branco são normalizados para "-".
    - Retorno de erros padronizado: {linha, numero_patrimonial, campo, mensagem}.
    """

    NEW_FMT_RE = r"^\d{3}\.\d{9}-\d$"

    # Campo com widget DecimalWidget explícito para aceitar vírgula como separador decimal.
    # A normalização vírgula→ponto é feita no before_import_row antes de chegar aqui.
    valor_unitario = resources.Field(
        column_name="valor_unitario",
        attribute="valor_unitario",
        widget=DecimalWidget(),
    )

    class Meta:
        model = BemPatrimonial
        fields = (
            "numero_patrimonial",
            "nome",
            "descricao",
            "valor_unitario",
            "marca",
            "modelo",
        )
        export_order = fields
        # "id" como import_id_fields faz o pipeline de hidratação funcionar corretamente,
        # enquanto get_instance retornando None garante que sempre será criado um novo registro.
        import_id_fields = ["id"]
        skip_unchanged = False
        report_skipped = False

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)
        self._erros_por_linha: list[dict] = []
        self._mensagens_exibidas = False

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _normalizar_valor(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def _linha_completamente_vazia(self, row) -> bool:
        """
        True quando TODAS as células da linha estão em branco (None, vazio ou
        só espaços). Linhas assim são descartadas silenciosamente na
        importação; linhas parcialmente preenchidas NÃO entram aqui e seguem
        para a validação normal (podendo gerar erro por campo obrigatório).
        """
        return all(
            self._normalizar_valor(row.get(coluna)) == ""
            for coluna in COLUNAS_MODELO
        )

    def _remover_linhas_vazias(self, dataset):
        """
        Remove do dataset (in place) as linhas 100% vazias, para que a
        importação processe apenas as linhas preenchidas. Retorna a quantidade
        de linhas removidas. Percorre de trás para frente para não invalidar os
        índices durante a remoção.
        """
        removidas = 0
        linhas = dataset.dict
        for idx in range(len(linhas) - 1, -1, -1):
            if self._linha_completamente_vazia(linhas[idx]):
                del dataset[idx]
                removidas += 1
        return removidas

    def _registrar_erro(self, linha: int, numero_patrimonial: str, campo: str, mensagem: str):
        """Registra erro padronizado: {linha, numero_patrimonial, campo, mensagem}"""
        self._erros_por_linha.append({
            "linha": linha,
            "numero_patrimonial": numero_patrimonial or "-",
            "campo": campo,
            "mensagem": mensagem,
        })

    def _parse_valor_unitario(self, raw: str, linha: int, numero_patrimonial: str):
        """Converte string para Decimal. Registra erro e retorna None se inválido."""
        if not raw:
            self._registrar_erro(linha, numero_patrimonial, "valor_unitario", "Campo obrigatório.")
            return None
        try:
            from decimal import Decimal, InvalidOperation
            normalizado = raw.strip().replace(".", "").replace(",", ".")
            valor = Decimal(normalizado)
        except (InvalidOperation, ValueError):
            self._registrar_erro(
                linha, numero_patrimonial, "valor_unitario",
                "Valor inválido. Use o formato 0,00 ou 0.000,00."
            )
            return None
        if valor < 0:
            self._registrar_erro(
                linha, numero_patrimonial, "valor_unitario",
                "O valor unitário não pode ser negativo."
            )
            return None
        return valor

    # ------------------------------------------------------------------
    # Validação completa do dataset — tudo ou nada (Ponto 2 e 3)
    # ------------------------------------------------------------------

    def _validar_cabecalho(self, dataset):
        """Verifica se as colunas correspondem exatamente ao modelo."""
        headers = {str(h).strip().lower() for h in (dataset.headers or [])}
        esperados = set(COLUNAS_MODELO)
        faltando = esperados - headers
        extras = headers - esperados
        if faltando or extras:
            partes = []
            if faltando:
                partes.append(f"colunas faltando: {', '.join(sorted(faltando))}")
            if extras:
                partes.append(f"colunas não esperadas: {', '.join(sorted(extras))}")
            return f"Cabeçalho inválido — {'; '.join(partes)}. Use o modelo oficial."
        return None

    def _validar_campos_obrigatorios(self, idx, numero_patrimonial, row):
        """Valida campos obrigatórios de texto de uma linha.

        marca e modelo NÃO são validados aqui — valores vazios são normalizados
        para "-" no before_import_row (regra de negócio definida na história).
        """
        msg = "Campo obrigatório."
        for campo in ("nome", "descricao"):
            if not self._normalizar_valor(row.get(campo)):
                self._registrar_erro(idx, numero_patrimonial, campo, msg)

    def _validar_numero_patrimonial(self, idx, numero_patrimonial, numeros_vistos):
        """Valida duplicidade do número patrimonial no arquivo e no banco."""
        if not numero_patrimonial:
            return

        numero_key = numero_patrimonial.lower()
        linha_anterior = numeros_vistos.get(numero_key)

        if linha_anterior:
            self._registrar_erro(
                idx, numero_patrimonial, "numero_patrimonial",
                f"Número patrimonial duplicado no arquivo. "
                f"Primeira ocorrência na linha {linha_anterior}."
            )
            return

        numeros_vistos[numero_key] = idx

        if BemPatrimonial.objects.filter(
            numero_patrimonial__iexact=numero_patrimonial
        ).exists():
            self._registrar_erro(
                idx, numero_patrimonial, "numero_patrimonial",
                "Número patrimonial já cadastrado no sistema."
            )

    def _validar_dataset_completo(self, dataset):
        """
        Valida TODAS as linhas antes de salvar qualquer uma.
        Implementa tudo-ou-nada: acumula todos os erros e retorna a lista.
        """
        self._erros_por_linha = []
        numeros_vistos: dict[str, int] = {}

        for idx, row in enumerate(dataset.dict, start=1):
            numero_patrimonial = self._normalizar_valor(row.get("numero_patrimonial"))
            valor_raw = self._normalizar_valor(row.get("valor_unitario"))

            self._validar_campos_obrigatorios(idx, numero_patrimonial, row)
            self._parse_valor_unitario(valor_raw, idx, numero_patrimonial)
            self._validar_numero_patrimonial(idx, numero_patrimonial, numeros_vistos)

        return self._erros_por_linha

    # ------------------------------------------------------------------
    # Hooks do django-import-export
    # ------------------------------------------------------------------

    def _ua_para_importacao(self):
        """
        Unidade Administrativa de destino dos bens importados.

        No resource base (usado pelo Django Admin) é sempre a UA do usuário
        autenticado. Subclasses (ex.: o resource da API) podem sobrescrever
        para suportar uma UA escolhida explicitamente.
        """
        return getattr(self.request.user, "unidade_administrativa", None)

    def before_import(self, dataset, *args, **kwargs):
        """
        Valida contexto do usuário e o dataset completo antes de processar qualquer linha.
        Tudo ou nada: qualquer erro rejeita a carga inteira.
        """
        self._erros_por_linha = []
        self._mensagens_exibidas = False

        if not self.request:
            return

        ua_usuario = self._ua_para_importacao()
        if not ua_usuario:
            raise ValidationError(
                "Não é possível importar bens: seu usuário não possui uma "
                "Unidade Administrativa vinculada. "
                "Entre em contato com o gestor de patrimônio."
            )
        if not ua_usuario.is_ativa:
            raise ValidationError(
                f"Não é possível importar bens: sua Unidade Administrativa "
                f"'{ua_usuario.nome}' está inativa. "
                "Entre em contato com o gestor de patrimônio."
            )

        if len(dataset) == 0:
            raise ValidationError("A planilha está vazia ou não contém linhas de dados.")

        erro_cabecalho = self._validar_cabecalho(dataset)
        if erro_cabecalho:
            raise ValidationError(erro_cabecalho)

        # Descarta linhas 100% vazias antes de validar/importar: apenas as
        # linhas preenchidas seguem adiante. Linhas parcialmente preenchidas
        # permanecem e são validadas normalmente (campo obrigatório em branco
        # continua sendo erro).
        self._remover_linhas_vazias(dataset)

        # Após remover as linhas vazias, a planilha pode ter ficado sem nenhuma
        # linha de dados — trata como planilha vazia.
        if len(dataset) == 0:
            raise ValidationError("A planilha está vazia ou não contém linhas de dados.")

        erros = self._validar_dataset_completo(dataset)
        if erros:
            if self.request:
                qtd = len(erros)
                messages.error(
                    self.request,
                    f"Importação rejeitada: {qtd} linha(s) com erro. Nenhum bem foi importado."
                )
                for erro in erros[:20]:
                    messages.warning(
                        self.request,
                        f"Linha {erro['linha']} | {erro['numero_patrimonial']} | "
                        f"{erro['campo']}: {erro['mensagem']}"
                    )
                if qtd > 20:
                    messages.warning(
                        self.request,
                        f"Existem mais {qtd - 20} linha(s) com erro além das listadas acima."
                    )
            raise ValidationError(
                f"Importação rejeitada: {len(erros)} linha(s) com erro. "
                "Corrija o arquivo e tente novamente."
            )

    def before_import_row(self, row, row_number=None, **kwargs):
        """Força status, limpa ID, normaliza marca/modelo e valor_unitario."""
        # Remove colunas que não fazem parte do modelo de importação para
        # evitar que o django-import-export tente mapeá-las (ex: id, status
        # presentes em planilhas exportadas pelo próprio sistema).
        for header in row.keys():
            if header.lower() not in COLUNAS_MODELO:
                del row[header]

        # Ponto 4: marca e modelo vazios → "-"
        for campo in ("marca", "modelo"):
            valor = self._normalizar_valor(row.get(campo))
            row[campo] = valor if valor else "-"

        # Normaliza valor_unitario: "2,50" → "2.50" para o DecimalWidget
        if "valor_unitario" in row:
            raw = self._normalizar_valor(row.get("valor_unitario"))
            if raw:
                row["valor_unitario"] = raw.replace(".", "").replace(",", ".")

    def get_instance(self, instance_loader, row):
        # Sempre retorna None para forçar criação de novo registro.
        return None

    def before_save_instance(self, instance, *args, **kwargs):
        instance.pk = None
        instance.id = None
        if self.request:
            if not instance.criado_por_id:
                instance.criado_por = self.request.user
            instance.unidade_administrativa = self._ua_para_importacao()
        instance.status = constants.AGUARDANDO_APROVACAO
        numero_patrimonial = self._normalizar_valor(instance.numero_patrimonial)
        if not numero_patrimonial:
            instance.numero_patrimonial = None
            instance.sem_numeracao = True
            instance.numero_formato_antigo = False
            return
        instance.sem_numeracao = False
        instance.numero_formato_antigo = not bool(
            re.fullmatch(self.NEW_FMT_RE, numero_patrimonial)
        )

    def after_import(self, dataset, result, *args, **kwargs):
        super().after_import(dataset, result, *args, **kwargs)


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
        StatusBemPatrimonialFilter,
        SemNumeroFilter,
        "numero_formato_antigo",
        ("criado_em", DateRangeFilter),
        BaixadosMaisDeUmPeriodoFilter,
        BuscaGeralTodasUOsFilter,
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
        actions.pop("delete_selected", None)
        if not request.user.is_gestor_patrimonio:
            actions.pop("aplicar_extracao_numero", None)
            actions.pop("aprovar_bens", None)
            actions.pop("reprovar_bens", None)
        return actions

    def delete_view(self, request, object_id, extra_context=None):
        obj = self.get_object(request, object_id)

        if obj is None:
            return HttpResponseRedirect(
                reverse(
                    f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
                )
            )

        if not self.has_delete_permission(request, obj=obj):
            raise PermissionDenied

        if request.method == "POST":
            with transaction.atomic():
                obj.delete()
            messages.success(request, _("Bem patrimonial apagado com sucesso."))
            return HttpResponseRedirect(
                reverse(
                    f"admin:{self.model._meta.app_label}_{self.model._meta.model_name}_changelist"
                )
            )

        context = {
            **self.admin_site.each_context(request),
            "object": obj,
            "opts": self.model._meta,
            "title": _("Confirmar exclusão"),
        }
        if extra_context:
            context.update(extra_context)

        return TemplateResponse(
            request,
            "admin/bem_patrimonial/bem_delete_confirm.html",
            context,
        )

    def get_list_display(self, request):
        return ("numero_patrimonial", "nome", "unidade_administrativa", "status")

    def get_readonly_fields(self, request, obj=None):
        base = ("status", "criado_por", "criado_em")

        if obj is None:
            return base

        if request.user.is_gestor_patrimonio:
            return base

        if request.user.is_operador_inventario:
            return base + (
                "unidade_administrativa",
                "numero_patrimonial",
                "numero_formato_antigo",
                "nome",
                "descricao",
                "valor_unitario",
                "marca",
                "modelo",
                "numero_processo",
                "foto",
                "justificativa",
            )

        return base + (
            "unidade_administrativa",
            "nome",
            "descricao",
            "valor_unitario",
            "marca",
            "modelo",
            "localizacao",
            "numero_processo",
            "foto",
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
            "numero_processo",
            "observacao",
            "justificativa",
        ]

        if request.user.is_operador_inventario:
            base = [f for f in base if f != "justificativa"]

        if obj:
            base = [f for f in base if f != "cadastro_modo"]
        else:
            base = [f for f in base if f != "justificativa"]

        return base

    autocomplete_fields = ("unidade_administrativa",)
    ordering = ("-criado_em",)

    inlines = [HistoricoGeralInline]

    def _usuario_pode_editar_obj(self, user, obj):
        if user.is_superuser:
            return True
        qs = BemPatrimonial.objects.filter(pk=obj.pk)
        qs = filtrar_queryset_bem_por_escopo_com_transferencia(user, qs)
        return qs.exists()

    def has_view_permission(self, request, obj=None):
        perm = super().has_view_permission(request, obj)
        if not perm:
            return False

        if obj is None:
            return True

        if request.user.is_superuser:
            return True

        if request.user.is_gestor_patrimonio or request.user.is_operador_inventario:
            return True

        return self._usuario_pode_editar_obj(request.user, obj)

    def get_object(self, request, object_id, from_field=None):
        obj = super().get_object(request, object_id, from_field)
        if obj is not None:
            return obj

        if (
            request.user.is_superuser
            or request.user.is_gestor_patrimonio
            or request.user.is_operador_inventario
        ):
            base_qs = self.model._default_manager.all()
            model_field = from_field or self.model._meta.pk.attname
            try:
                return base_qs.get(**{model_field: object_id})
            except self.model.DoesNotExist:
                return None
            except (ValueError, ValidationError):
                return None

        return None

    def has_change_permission(self, request, obj=None):
        perm = super().has_change_permission(request, obj)
        if not perm:
            return False

        if obj and not self._usuario_pode_editar_obj(request.user, obj):
            return False

        if obj and getattr(obj, "excluido", False):
            return False

        if obj and obj.status in constants.STATUS_FINAIS_BEM:
            return False

        return True

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return False

        if getattr(obj, "excluido", False):
            return False

        if not request.user.is_gestor_patrimonio:
            return False

        if obj.status in constants.STATUS_FINAIS_BEM:
            return False

        if not validar_objeto_no_escopo(
            request.user, obj, campo_ua="unidade_administrativa"
        ):
            return False

        return True

    def _setup_create_form_ua_field(self, self_inner, request):
        if "unidade_administrativa" not in self_inner.fields:
            return
        self_inner.fields["justificativa"].required = False
        modo = (getattr(self_inner, "data", None) or {}).get("cadastro_modo") or (
            getattr(self_inner, "initial", {}) or {}
        ).get("cadastro_modo")
        if modo == "multi" and "localizacao" in self_inner.fields:
            self_inner.fields["localizacao"].required = False
        fld = self_inner.fields["unidade_administrativa"]
        fld.required = True
        qs_ativas = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        )
        fld.queryset = filtrar_ua_origem_por_escopo(request.user, qs_ativas)
        ua_user = getattr(request.user, "unidade_administrativa", None)
        if ua_user and not usuario_e_super_admin(request.user):
            fld.initial = ua_user
            fld.disabled = True

    def _validate_create_form_ua(self, cleaned_data, request):
        ua_form = cleaned_data.get("unidade_administrativa")
        if not ua_form:
            raise ValidationError(
                {"unidade_administrativa": "Selecione a Unidade Administrativa."}
            )
        if ua_form.status != UnidadeAdministrativa.ATIVA:
            raise ValidationError(
                {
                    "unidade_administrativa": "A Unidade Administrativa selecionada está inativa."
                }
            )
        qs_ativas = UnidadeAdministrativa.objects.filter(
            status=UnidadeAdministrativa.ATIVA
        )
        qs_permitidas = filtrar_ua_origem_por_escopo(request.user, qs_ativas)
        if not qs_permitidas.filter(pk=ua_form.pk).exists():
            raise ValidationError(
                {
                    "unidade_administrativa": "Você não tem permissão para usar essa Unidade Administrativa."
                }
            )
        ua_user = getattr(request.user, "unidade_administrativa", None)
        if ua_user and not ua_user.is_ativa:
            raise ValidationError(
                f"Não é possível criar bens patrimoniais. Sua unidade administrativa "
                f"'{ua_user.nome}' está inativa. Entre em contato com o gestor de patrimônio."
            )

    def _validate_edit_form_ua(self, cleaned, instance, user):
        if not instance or not instance.pk:
            return
        ua_original = instance.unidade_administrativa
        ua_post = cleaned.get("unidade_administrativa") or ua_original
        if ua_post != ua_original:
            raise ValidationError(
                {
                    "unidade_administrativa": "Não é permitido alterar a Unidade Administrativa na edição."
                }
            )
        if not ua_post:
            raise ValidationError(
                {"unidade_administrativa": "Unidade Administrativa é obrigatória."}
            )

        if not user.is_operador_inventario:
            nome_original = instance.nome
            nome_post = cleaned.get("nome")

            numero_original = instance.numero_patrimonial
            numero_post = cleaned.get("numero_patrimonial")

            justificativa = cleaned.get("justificativa")

            nome_alterado = nome_post != nome_original
            numero_alterado = numero_post != numero_original

            if (nome_alterado or numero_alterado) and not justificativa:
                msg = (
                    "A justificativa é obrigatória quando o Nome ou "
                    "o Número Patrimonial forem alterados."
                )
                raise ValidationError(
                    {
                        "justificativa": msg,
                        "nome": msg,
                        "numero_patrimonial": msg,
                    }
                )

    def get_form(self, request, obj=None, **kwargs):
        base_form = super().get_form(request, obj, **kwargs)

        if obj is None:
            original_clean = base_form.clean
            admin = self

            class CreateForm(base_form):
                def __init__(self_inner, *a, **kw):
                    super().__init__(*a, **kw)
                    admin._setup_create_form_ua_field(self_inner, request)

                def clean(self_inner):
                    cleaned_data = original_clean(self_inner)
                    admin._validate_create_form_ua(cleaned_data, request)
                    return cleaned_data

            return CreateForm

        admin_ref = self

        class EditForm(base_form):
            def __init__(self_inner, *a, **kw):
                super().__init__(*a, **kw)
                if "unidade_administrativa" in self_inner.fields:
                    self_inner.fields["unidade_administrativa"].disabled = True
                    self_inner.fields["unidade_administrativa"].required = True

                if not request.user.is_operador_inventario:
                    self_inner.fields["justificativa"].required = False

            def clean(self_inner):
                cleaned = super().clean()
                admin_ref._validate_edit_form_ua(
                    cleaned, getattr(self_inner, "instance", None), request.user
                )
                return cleaned

        return EditForm

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            original = BemPatrimonial.objects.get(pk=obj.pk)
            if original.status in constants.STATUS_FINAIS_BEM:
                raise ValidationError(
                    f"Este bem está com status '{original.get_status_display()}' e não pode ser editado."
                )
        if obj.id is None:
            obj.criado_por = request.user
            if not obj.status:
                obj.status = constants.AGUARDANDO_APROVACAO
        try:
            obj._justificativa = request.POST.get("justificativa") or None
            super().save_model(request, obj, form, change)
        except IntegrityError as e:
            if "numero_patrimonial" in str(e).lower():
                form.add_error(
                    "numero_patrimonial",
                    "Não foi possível salvar. O Número Patrimonial já está cadastrado no sistema.",
                )
                return
            raise

    def _anotar_baixa_data(self, queryset):
        baixa_data_sq = (
            BaixaFisicaBensItem.objects.filter(bem_id=OuterRef("pk"))
            .order_by("-baixa__data_baixa")
            .values("baixa__data_baixa")[:1]
        )
        return queryset.annotate(
            baixa_data=Subquery(baixa_data_sq),
        )

    def _deve_aplicar_filtro_padrao_baixados(self, request):
        return "baixados_mais_de_um_periodo" not in request.GET

    def _aplicar_filtro_padrao_baixados(self, queryset):
        ano_corrente = timezone.localdate().year
        ano_limite = ano_corrente - 1

        return queryset.exclude(
            status=constants.BAIXA_FISICA,
            baixa_data__year__lt=ano_limite,
        )

    def _deve_aplicar_busca_geral_todas_uos(self, request):
        return request.GET.get("busca_geral_todas_uos") == "1"

    def _get_queryset_com_auditoria(self, request, aplicar_escopo=True):
        qs = (
            super()
            .get_queryset(request)
            .select_related("unidade_administrativa", "criado_por")
        )

        if aplicar_escopo:
            qs = filtrar_queryset_bem_por_escopo_com_transferencia(request.user, qs)

        qs = self._anotar_baixa_data(qs)

        ct = ContentType.objects.get_for_model(BemPatrimonial)
        pk_as_char = Cast(OuterRef("pk"), output_field=models.CharField())

        hist_qs = HistoricoGeral.objects.filter(
            content_type=ct, object_id=pk_as_char
        ).order_by("-alterado_em")

        return qs.annotate(
            audit_last_at=Subquery(hist_qs.values("alterado_em")[:1]),
            audit_last_by_id=Subquery(hist_qs.values("alterado_por_id")[:1]),
        )

    def _buscar_com_baixados_antigos(self, request, search_term):
        queryset_ampliado = self._get_queryset_com_auditoria(request)

        if StatusBemPatrimonialFilter.deve_ocultar_transferidos(request):
            queryset_ampliado = queryset_ampliado.exclude(
                status=constants.TRANSFERIDO
            )

        qs, use_distinct = super().get_search_results(
            request, queryset_ampliado, search_term
        )

        qs = filtrar_queryset_por_escopo(
            usuario=request.user,
            queryset=qs,
            campo_ua="unidade_administrativa",
        )

        return qs, use_distinct

    def get_queryset(self, request):
        qs = self._get_queryset_com_auditoria(
            request,
            aplicar_escopo=not self._deve_aplicar_busca_geral_todas_uos(request),
        )

        if self._deve_aplicar_filtro_padrao_baixados(request):
            qs = self._aplicar_filtro_padrao_baixados(qs)

        return qs

    def get_export_queryset(self, request):
        queryset = super().get_export_queryset(request)
        if not self._deve_aplicar_busca_geral_todas_uos(request):
            queryset = filtrar_queryset_por_escopo(
                usuario=request.user,
                queryset=queryset,
                campo_ua="unidade_administrativa",
            )

        queryset = self._anotar_baixa_data(queryset)

        if "baixados_mais_de_um_periodo" not in request.GET:
            queryset = self._aplicar_filtro_padrao_baixados(queryset)

        return queryset

    def get_import_formats(self):
        """Restringe a importação a CSV, XLS e XLSX — alinhado com a API."""
        return [CSV, XLS, XLSX]

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

    def _add_view_multi_base_data(self, form):
        base = {
            "status": form.cleaned_data.get("status") or constants.AGUARDANDO_APROVACAO,
            "unidade_administrativa": form.cleaned_data.get("unidade_administrativa"),
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
                base["status"] = BemPatrimonial._meta.get_field("status").get_default()
            except Exception:
                fld = BemPatrimonial._meta.get_field("status")
                if getattr(fld, "choices", None):
                    base["status"] = fld.choices[0][0]
        return base

    def _add_view_multi_parse_payload(self, request):
        import json

        raw = request.POST.get("multi_payload") or "[]"
        try:
            return json.loads(raw)
        except Exception:
            return []

    def _add_view_multi_to_bool(self, v):
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        return str(v).strip().lower() in ("1", "true", "on", "yes", "y", "t")

    def _add_view_multi_process_row_validate_save(self, bem, idx):
        """Valida e salva o bem; retorna (bem, None) ou (None, mensagem_erro)."""
        try:
            bem.full_clean()
            bem.save()
            return bem, None
        except ValidationError as ve:
            err_msgs = (
                "; ".join(f"{k}: {', '.join(v)}" for k, v in ve.message_dict.items())
                if hasattr(ve, "message_dict")
                else str(ve)
            )
            return None, f"Linha {idx}: {err_msgs}"
        except IntegrityError as ie:
            return None, f"Linha {idx}: {str(ie)}"
        except Exception as ex:
            return None, f"Linha {idx}: Erro inesperado: {str(ex)}"

    def _add_view_multi_process_row(self, request, idx, row, base):
        localizacao = (row.get("localizacao") or "").strip() or None
        if not localizacao:
            return None, f"Linha {idx}: Informe a Localização (obrigatória)."

        numero_patrimonial_raw = (row.get("numero_patrimonial") or "").strip()
        numero_formato_antigo = self._add_view_multi_to_bool(
            row.get("numero_formato_antigo")
        )
        sem_numeracao = self._add_view_multi_to_bool(row.get("sem_numeracao"))
        numero_patrimonial = None if sem_numeracao else (numero_patrimonial_raw or None)
        bem = BemPatrimonial(
            criado_por=request.user,
            numero_patrimonial=numero_patrimonial,
            numero_formato_antigo=numero_formato_antigo,
            sem_numeracao=sem_numeracao,
            localizacao=localizacao,
            **base,
        )
        return self._add_view_multi_process_row_validate_save(bem, idx)

    def _add_view_multi_process_linhas(self, request, linhas, base):
        criados, errors = [], []
        with transaction.atomic():
            for idx, row in enumerate(linhas, start=1):
                bem, erro = self._add_view_multi_process_row(request, idx, row, base)
                if erro:
                    errors.append(erro)
                elif bem:
                    criados.append(bem)
            if errors:
                transaction.set_rollback(True)
        return criados, errors

    def _add_view_handle_multi_post(self, request, form_url, extra_context):
        post = request.POST.copy()
        post["cadastro_modo"] = "multi"
        post["sem_numeracao"] = "on"
        post["numero_patrimonial"] = ""
        post["numero_formato_antigo"] = ""
        form_cls = self.get_form(request)
        form = form_cls(post, request.FILES)
        if not form.is_valid():
            return super().add_view(request, form_url, extra_context)
        linhas = self._add_view_multi_parse_payload(request)
        if not linhas:
            form.add_error(None, "Adicione ao menos uma linha no modo Múltiplos Bens.")
            return super().add_view(request, form_url, extra_context)
        base = self._add_view_multi_base_data(form)
        criados, errors = self._add_view_multi_process_linhas(request, linhas, base)
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

    def add_view(self, request, form_url="", extra_context=None):
        """
        Intercepta o POST no modo 'multi': valida form base, payload das linhas e cria N bens.
        """
        if request.method == "POST" and request.POST.get("cadastro_modo") == "multi":
            return self._add_view_handle_multi_post(request, form_url, extra_context)
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
            if HTML_END_FORM_CONTAINER in html:
                html = html.replace(
                    HTML_END_FORM_CONTAINER,
                    anchor + HTML_END_FORM_CONTAINER,
                )
            elif HTML_END_FORM in html:
                html = html.replace(HTML_END_FORM, anchor + HTML_END_FORM)
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
        user_model = get_user_model()
        try:
            u = user_model.objects.only("first_name", "last_name", "username").get(
                id=user_id
            )
            return u.get_full_name() or u.username
        except user_model.DoesNotExist:
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
                '<img src="{}" style="height:48px;width:48px;object-fit:cover;border-radius:6px;border:1px solid #e5e7eb;" />',  # noqa E501
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
                    '<img src="{}" style="max-height:200px;border-radius:8px;border:1px solid #e5e7eb;padding:4px;background:#fff;" />'  # noqa E501
                    "</a>",
                    obj.foto.url,
                    obj.foto.url,
                )
        except Exception:
            pass
        return "—"

    def _aplicar_filtros_autocomplete_bem(self, request, qs, use_distinct):
        app_label = request.GET.get("app_label")
        model_name = request.GET.get("model_name")
        field_name = request.GET.get("field_name")

        if not (
            app_label == "bem_patrimonial"
            and model_name
            in ("movimentacaobensitem", "baixafisicabensitem", "transferenciabensitem")
            and field_name == "bem"
        ):
            return qs, use_distinct

        qs = qs.filter(status=constants.APROVADO)

        if model_name == "transferenciabensitem":
            uo_referencia_id = obter_unidade_orcamentaria_id_do_usuario(request.user)
            if not uo_referencia_id:
                return qs.none(), use_distinct

            qs = qs.filter(
                unidade_administrativa__unidade_orcamentaria_id=uo_referencia_id
            )

            ua_origem = request.GET.get("ua_origem")
            uo_origem = request.GET.get("uo_origem")
            if ua_origem:
                qs = qs.filter(unidade_administrativa_id=ua_origem)
            elif uo_origem and str(uo_origem) != str(uo_referencia_id):
                return qs.none(), use_distinct

            qs = qs.annotate(
                autocomplete_label_transferencia=Concat(
                    "unidade_administrativa__codigo",
                    models.Value(" - "),
                    "unidade_administrativa__sigla",
                    models.Value(" | "),
                    "numero_patrimonial",
                    models.Value(" - "),
                    "nome",
                    output_field=models.CharField(),
                )
            )
        else:
            ua_origem = request.GET.get("ua_origem")
            if not ua_origem:
                return qs.none(), use_distinct
            qs = qs.filter(unidade_administrativa_id=ua_origem)

        exclude_bens = request.GET.get("exclude_bens")
        if not exclude_bens:
            return qs, use_distinct

        ids = [int(pk) for pk in exclude_bens.split(",") if pk.isdigit()]
        if ids:
            qs = qs.exclude(pk__in=ids)

        return qs, use_distinct

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)

        if getattr(request, "_busca_com_baixados_antigos", False):
            params = request.GET.copy()
            params["baixados_mais_de_um_periodo"] = "1"
            return HttpResponseRedirect(f"{request.path}?{params.urlencode()}")

        return response

    def get_search_results(self, request, queryset, search_term):
        request._busca_com_baixados_antigos = False

        qs, use_distinct = super().get_search_results(request, queryset, search_term)

        if request.path.endswith("/autocomplete/"):
            if request.GET.get("model_name") != "transferenciabensitem":
                qs = filtrar_queryset_por_escopo(
                    usuario=request.user,
                    queryset=qs,
                    campo_ua="unidade_administrativa",
                )
            return self._aplicar_filtros_autocomplete_bem(
                request, qs, use_distinct
            )

        if not self._deve_aplicar_busca_geral_todas_uos(request):
            qs = filtrar_queryset_bem_por_escopo_com_transferencia(request.user, qs)

        if (
            search_term
            and "baixados_mais_de_um_periodo" not in request.GET
            and not qs.exists()
        ):
            request._busca_com_baixados_antigos = True
            return self._buscar_com_baixados_antigos(request, search_term)

        return qs, use_distinct
