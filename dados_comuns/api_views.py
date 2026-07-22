from collections import defaultdict
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import (
    NotFound,
    ValidationError as DRFValidationError,
)
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from dados_comuns.api_serializers import (
    UnidadeAdministrativaDetailSerializer,
    UnidadeAdministrativaExportQuerySerializer,
    UnidadeAdministrativaHistoricoGrupoSerializer,
    UnidadeAdministrativaListSerializer,
    UnidadeOrcamentariaDetailSerializer,
    UnidadeOrcamentariaExportQuerySerializer,
    UnidadeOrcamentariaHistoricoGrupoSerializer,
    UnidadeOrcamentariaListSerializer,
)
from dados_comuns.context import audit_as
from dados_comuns.escopo import filtrar_queryset_usuario_por_escopo
from dados_comuns.formats import (
    UnidadeAdministrativaPDFFormat,
    UnidadeOrcamentariaPDFFormat,
)
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa, UnidadeOrcamentaria
from dados_comuns.permissions import (
    UnidadeAdministrativaPermission,
    UnidadeOrcamentariaPermission,
)
from dados_comuns.libs.pagination import SafePagination
from dados_comuns.resources import (
    UnidadeAdministrativaResource,
    UnidadeOrcamentariaResource,
)
from dados_comuns.utils import dict_changes, garantir_ua_ponto_central_externa
from usuario.serializers import UnidadeAdministrativaUsuarioSerializer


User = get_user_model()


UA_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da unidade administrativa.",
)

# Configuração da busca/ordenação do sub-recurso de usuários associados à UA
# (GET /unidades-administrativas/{id}/usuarios/). Mantida isolada da
# configuração de search_fields/ordering_fields do UnidadeAdministrativaViewSet
# para não afetar a listagem/exportação de UAs.
UA_USUARIOS_ORDERING_FIELDS = ["id", "nome", "username", "rf"]
UA_USUARIOS_DEFAULT_ORDERING = ["nome"]

UO_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da unidade orçamentária.",
)


class AuditHistoryExportMixin:
    audit_model = None
    historico_grupo_serializer_class = None
    export_query_serializer_class = None
    export_resource_class = None
    export_pdf_format_class = None
    export_filename_prefix = ""

    def _get_audit_content_type(self):
        return ContentType.objects.get_for_model(self.audit_model)

    def _audit_changes(self, obj, original=None, operation="update"):
        ct = self._get_audit_content_type()

        if operation == "update" and original is not None:
            changes = dict_changes(
                original,
                obj,
                fields=self.AUDIT_TRACK_FIELDS,
            )
            if not changes:
                return

            HistoricoGeral.objects.bulk_create(
                [
                    HistoricoGeral(
                        content_type=ct,
                        object_id=str(obj.pk),
                        campo=field,
                        valor_antigo=old,
                        valor_novo=new,
                        alterado_por=self.request.user,
                    )
                    for field, (old, new) in changes.items()
                ]
            )
            return

        if operation == "create":
            HistoricoGeral.objects.create(
                content_type=ct,
                object_id=str(obj.pk),
                campo="acao",
                valor_antigo="",
                valor_novo="criado",
                alterado_por=self.request.user,
            )
            return

        if operation == "delete":
            HistoricoGeral.objects.create(
                content_type=ct,
                object_id=str(obj.pk),
                campo="acao",
                valor_antigo="existente",
                valor_novo="excluido",
                alterado_por=self.request.user,
            )

    def _build_historico_response(self, instance):
        historicos = (
            HistoricoGeral.objects.filter(
                content_type=self._get_audit_content_type(),
                object_id=str(instance.pk),
            )
            .select_related("alterado_por")
            .order_by("-alterado_em")
        )

        agrupado = defaultdict(list)
        for item in historicos:
            chave = (item.alterado_em.replace(microsecond=0), item.alterado_por_id)
            agrupado[chave].append(item)

        resposta = []
        for (alterado_em, alterado_por_id), itens in agrupado.items():
            resposta.append(
                {
                    "alterado_em": alterado_em,
                    "alterado_por": alterado_por_id,
                    "alterado_por_nome": (
                        itens[0].alterado_por.nome if itens[0].alterado_por else None
                    ),
                    "acoes": [
                        {
                            "campo": i.campo,
                            "valor_antigo": i.valor_antigo,
                            "valor_novo": i.valor_novo,
                        }
                        for i in itens
                    ],
                }
            )

        resposta_ordenada = sorted(
            resposta,
            key=lambda row: row["alterado_em"],
            reverse=True,
        )

        serializer = self.historico_grupo_serializer_class(
            resposta_ordenada,
            many=True,
        )
        return Response(serializer.data)

    def _build_export_response(self, request):
        serializer = self.export_query_serializer_class(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        formato = serializer.validated_data["formato"]

        queryset = self.filter_queryset(self.get_queryset())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.export_filename_prefix}_{timestamp}.{formato}"

        if formato == "pdf":
            pdf_format = self.export_pdf_format_class()
            pdf_format._export_request = request
            pdf_format._export_queryset = queryset
            pdf_bytes = pdf_format.export_data(None)

            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        resource = self.export_resource_class()
        dataset = resource.export(queryset)

        if formato == "csv":
            content = dataset.csv.encode("utf-8-sig")
            content_type = "text/csv"
        elif formato == "xls":
            content = dataset.xls
            content_type = "application/vnd.ms-excel"
        else:
            content = dataset.xlsx
            content_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


@extend_schema_view(
    list=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Listar unidades orçamentárias",
        description="Lista paginada com busca, filtros e ordenação. Acesso restrito a superusuário.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Busca em: codigo, sigla e nome.",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Ordenação por: id, codigo, sigla, nome e ativa. Use '-' para descendente.",
            ),
            OpenApiParameter(
                name="ativa",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filtra por unidade orçamentária ativa/inativa.",
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Número da página.",
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Quantidade de itens por página (máximo 100).",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Lista retornada com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para acessar o recurso."),
        },
    ),
    retrieve=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Detalhar unidade orçamentária",
        parameters=[UO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Detalhe retornado com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para acessar o recurso."),
            404: OpenApiResponse(description="Unidade orçamentária não encontrada."),
        },
    ),
    create=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Criar unidade orçamentária",
        responses={
            201: OpenApiResponse(description="Unidade orçamentária criada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para criar."),
        },
    ),
    update=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Atualizar unidade orçamentária",
        parameters=[UO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Unidade orçamentária atualizada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para atualizar."),
            404: OpenApiResponse(description="Unidade orçamentária não encontrada."),
        },
    ),
    partial_update=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Atualizar parcialmente unidade orçamentária",
        parameters=[UO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Unidade orçamentária atualizada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para atualizar."),
            404: OpenApiResponse(description="Unidade orçamentária não encontrada."),
        },
    ),
    destroy=extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Excluir unidade orçamentária",
        description="A exclusão é permitida apenas para superusuário e bloqueada quando existirem vínculos ativos no sistema.",
        parameters=[UO_ID_PATH_PARAM],
        responses={
            204: OpenApiResponse(description="Unidade orçamentária excluída com sucesso."),
            400: OpenApiResponse(description="Não foi possível excluir por regra de integridade/vínculos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para excluir."),
            404: OpenApiResponse(description="Unidade orçamentária não encontrada."),
        },
    ),
)
class UnidadeOrcamentariaViewSet(AuditHistoryExportMixin, viewsets.ModelViewSet):
    permission_classes = [UnidadeOrcamentariaPermission]
    audit_model = UnidadeOrcamentaria
    historico_grupo_serializer_class = UnidadeOrcamentariaHistoricoGrupoSerializer
    export_query_serializer_class = UnidadeOrcamentariaExportQuerySerializer
    export_resource_class = UnidadeOrcamentariaResource
    export_pdf_format_class = UnidadeOrcamentariaPDFFormat
    export_filename_prefix = "unidades_orcamentarias"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["ativa"]
    search_fields = ["codigo", "sigla", "nome", "codigo_orgao", "sigla_orgao", "orgao"]
    ordering_fields = [
        "id",
        "codigo",
        "sigla",
        "nome",
        "codigo_orgao",
        "sigla_orgao",
        "orgao",
        "ativa",
    ]
    ordering = ["codigo", "nome"]

    AUDIT_TRACK_FIELDS = (
        "codigo",
        "sigla",
        "nome",
        "codigo_orgao",
        "sigla_orgao",
        "orgao",
        "ativa",
    )

    def get_serializer_class(self):
        if self.action == "list":
            return UnidadeOrcamentariaListSerializer
        return UnidadeOrcamentariaDetailSerializer

    def get_queryset(self):
        if getattr(self.request.user, "is_superuser", False):
            return UnidadeOrcamentaria.objects.all()

        return UnidadeOrcamentaria.objects.none()

    def _validar_exclusao_segura(self, instance):
        vinculos = instance.listar_vinculos_para_exclusao()
        if vinculos:
            raise DRFValidationError(
                {
                    "detail": "Não foi possível excluir esta Unidade Orçamentária porque existem vínculos ativos no sistema: {}.".format(
                        ", ".join(vinculos)
                    )
                }
            )

    def perform_create(self, serializer):
        with transaction.atomic():
            with audit_as(self.request.user):
                obj = serializer.save()
                garantir_ua_ponto_central_externa(obj)
            self._audit_changes(obj, operation="create")

    def perform_update(self, serializer):
        original = UnidadeOrcamentaria.objects.get(pk=serializer.instance.pk)

        with transaction.atomic():
            with audit_as(self.request.user):
                obj = serializer.save()
                garantir_ua_ponto_central_externa(obj)
            self._audit_changes(obj, original=original, operation="update")

    def perform_destroy(self, instance):
        self._validar_exclusao_segura(instance)

        with transaction.atomic():
            try:
                self._audit_changes(instance, operation="delete")
                with audit_as(self.request.user):
                    instance.delete()
            except ProtectedError:
                raise DRFValidationError(
                    {
                        "detail": "Não foi possível excluir esta Unidade Orçamentária porque existem vínculos ativos no sistema."
                    }
                )

    @extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Histórico da unidade orçamentária",
        description="Retorna o histórico de alterações da unidade orçamentária informada no ID.",
        parameters=[UO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(
                response=UnidadeOrcamentariaHistoricoGrupoSerializer(many=True),
                description="Histórico retornado com sucesso.",
            ),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para visualizar histórico."),
            404: OpenApiResponse(description="Unidade orçamentária não encontrada."),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="historico",
        filter_backends=[],
        pagination_class=None,
    )
    def historico(self, request, pk=None):
        return self._build_historico_response(self.get_object())

    @extend_schema(
        tags=["Unidades Orçamentárias"],
        summary="Exportar unidades orçamentárias",
        description="Exporta os dados filtrados para csv, xls, xlsx ou pdf.",
        parameters=[
            OpenApiParameter(
                name="formato",
                required=True,
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=["csv", "xls", "xlsx", "pdf"],
            )
        ],
        responses={
            200: OpenApiResponse(description="Arquivo de exportação gerado com sucesso."),
            400: OpenApiResponse(description="Parâmetros inválidos para exportação."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para exportar."),
        },
    )
    @action(detail=False, methods=["get"], url_path="exportar")
    def exportar(self, request):
        return self._build_export_response(request)


@extend_schema_view(
    list=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Listar unidades administrativas",
        description="Lista paginada com busca, filtros e ordenação.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Busca em: codigo, sigla, nome, unidade_orcamentaria__codigo e unidade_orcamentaria__nome.",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Ordenação por: id, codigo, sigla, nome, status, created_at, updated_at, unidade_orcamentaria__codigo. Use '-' para descendente.",
            ),
            OpenApiParameter(
                name="status",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Filtra por status da unidade administrativa (ativa/inativa).",
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Número da página.",
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Quantidade de itens por página (máximo 100).",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Lista retornada com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para acessar o recurso."),
        },
    ),
    retrieve=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Detalhar unidade administrativa",
        parameters=[UA_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Detalhe retornado com sucesso."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para acessar o recurso."),
            404: OpenApiResponse(description="Unidade administrativa não encontrada."),
        },
    ),
    create=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Criar unidade administrativa",
        description="Cria unidade administrativa. O campo 'codigo' deve receber apenas o sufixo numérico com 3 ou 4 dígitos (ex.: 002 ou 1002). O backend compõe o código final com o prefixo da unidade orçamentária (ex.: 01.16.10.002).",
        responses={
            201: OpenApiResponse(description="Unidade administrativa criada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para criar."),
        },
    ),
    update=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Atualizar unidade administrativa",
        parameters=[UA_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Unidade administrativa atualizada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para atualizar."),
            404: OpenApiResponse(description="Unidade administrativa não encontrada."),
        },
    ),
    partial_update=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Atualizar parcialmente unidade administrativa",
        parameters=[UA_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Unidade administrativa atualizada com sucesso."),
            400: OpenApiResponse(description="Dados inválidos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para atualizar."),
            404: OpenApiResponse(description="Unidade administrativa não encontrada."),
        },
    ),
    destroy=extend_schema(
        tags=["Unidades Administrativas"],
        summary="Excluir unidade administrativa",
        description="Somente superusuário ou gestor de patrimônio podem excluir. A exclusão pode falhar caso existam vínculos protegidos no banco (ex.: bens patrimoniais associados).",
        parameters=[UA_ID_PATH_PARAM],
        responses={
            204: OpenApiResponse(description="Unidade administrativa excluída com sucesso."),
            400: OpenApiResponse(description="Não foi possível excluir por regra de integridade/vínculos."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para excluir."),
            404: OpenApiResponse(description="Unidade administrativa não encontrada."),
        },
    ),
)
class UnidadeAdministrativaViewSet(AuditHistoryExportMixin, viewsets.ModelViewSet):
    permission_classes = [UnidadeAdministrativaPermission]
    audit_model = UnidadeAdministrativa
    historico_grupo_serializer_class = UnidadeAdministrativaHistoricoGrupoSerializer
    export_query_serializer_class = UnidadeAdministrativaExportQuerySerializer
    export_resource_class = UnidadeAdministrativaResource
    export_pdf_format_class = UnidadeAdministrativaPDFFormat
    export_filename_prefix = "unidades_administrativas"

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status"]
    search_fields = [
        "codigo",
        "sigla",
        "nome",
        "unidade_orcamentaria__codigo",
        "unidade_orcamentaria__nome",
    ]
    ordering_fields = [
        "id",
        "codigo",
        "sigla",
        "nome",
        "status",
        "created_at",
        "updated_at",
        "unidade_orcamentaria__codigo",
    ]
    ordering = ["unidade_orcamentaria__codigo", "codigo", "sigla", "nome"]

    AUDIT_TRACK_FIELDS = (
        "unidade_orcamentaria",
        "codigo",
        "sigla",
        "nome",
        "status",
    )

    @extend_schema(
        parameters=[
            UA_ID_PATH_PARAM,
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Busca por nome, usuário (username) ou RF.",
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Campo de ordenação. Aceita: id, nome, username, rf "
                    "(prefixo '-' para ordem decrescente). Padrão: nome."
                ),
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Itens por página (padrão 10, máximo 100).",
            ),
        ],
        responses={200: UnidadeAdministrativaUsuarioSerializer(many=True)},
        description=(
            "Lista os usuários associados à Unidade Administrativa (vínculo "
            "ativo e vínculos adicionais), com paginação, busca e ordenação, "
            "respeitando o mesmo escopo de visibilidade da listagem geral de "
            "usuários."
        ),
    )
    @action(detail=True, methods=["get"], url_path="usuarios")
    def usuarios(self, request, pk=None):
        """
        GET /unidades-administrativas/{id}/usuarios/

        Recupera os usuários vinculados à UA tanto pela FK ativa
        (``unidade_administrativa``) quanto pelo vínculo adicional M2M
        (``unidades_administrativas``), sem duplicidade.

        Não usamos ``self.get_object()`` (ver comentário abaixo): resolvemos
        o objeto diretamente, mas a MESMA checagem de escopo usada em
        retrieve/update (``_pode_acessar_objeto``) continua sendo aplicada.
        """
        # Não usamos self.get_object() aqui de propósito: ele passa pelo
        # self.filter_queryset(), que aplicaria o SearchFilter/OrderingFilter
        # de classe do UnidadeAdministrativaViewSet (search_fields =
        # codigo/sigla/nome da própria UA) sobre os MESMOS parâmetros
        # "search"/"ordering" que aqui são destinados aos usuários da UA —
        # podendo filtrar a UA para fora do queryset e gerar 404 indevido.
        # Resolvemos o objeto diretamente, preservando a mesma checagem de
        # escopo usada em retrieve/update.
        unidade = get_object_or_404(self.get_queryset(), pk=pk)
        if not self._pode_acessar_objeto(request.user, unidade):
            raise NotFound()

        # Resolve primeiro os IDs dos usuários vinculados à UA (FK ou M2M) e
        # só então monta o queryset final a partir deles. Isso evita manter
        # o JOIN do M2M "pendurado" no queryset enquanto aplicamos busca e
        # ordenação em seguida, o que poderia gerar duplicidade de linhas.
        usuario_ids = (
            filtrar_queryset_usuario_por_escopo(request.user, User.objects.all())
            .filter(
                Q(unidade_administrativa_id=unidade.id)
                | Q(unidades_administrativas__id=unidade.id)
            )
            .values_list("id", flat=True)
            .distinct()
        )
        queryset = User.objects.filter(id__in=list(usuario_ids))

        search_term = (request.query_params.get("search") or "").strip()
        if search_term:
            queryset = queryset.filter(
                Q(nome__icontains=search_term)
                | Q(username__icontains=search_term)
                | Q(rf__icontains=search_term)
            )

        ordering_param = request.query_params.get("ordering") or ""
        ordering_field = ordering_param.lstrip("-")
        if ordering_field not in UA_USUARIOS_ORDERING_FIELDS:
            ordering_param = ",".join(UA_USUARIOS_DEFAULT_ORDERING)
        queryset = queryset.order_by(*ordering_param.split(","))

        paginator = SafePagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = UnidadeAdministrativaUsuarioSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def get_serializer_class(self):
        if self.action == "list":
            return UnidadeAdministrativaListSerializer
        return UnidadeAdministrativaDetailSerializer

    def get_queryset(self):
        qs = UnidadeAdministrativa.objects.select_related("unidade_orcamentaria")

        user = self.request.user
        uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if uo_id:
            return qs.filter(unidade_orcamentaria_id=uo_id)

        ua_id = getattr(user, "unidade_administrativa_id", None)
        if ua_id:
            return qs.filter(pk=ua_id)

        return qs.none()

    def get_object(self):
        obj = super().get_object()
        if not self._pode_acessar_objeto(self.request.user, obj):
            raise NotFound()

        return obj

    def _pode_acessar_objeto(self, user, obj):
        user_uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if user_uo_id:
            return obj.unidade_orcamentaria_id == user_uo_id

        user_ua_id = getattr(user, "unidade_administrativa_id", None)
        if user_ua_id:
            return obj.pk == user_ua_id

        return False

    def _validate_uo_scope(self, validated_data, instance=None):
        user = self.request.user

        nova_uo = validated_data.get("unidade_orcamentaria")
        if instance is not None and nova_uo is None:
            nova_uo = instance.unidade_orcamentaria

        if nova_uo is None:
            raise DRFValidationError(
                {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
            )

        if getattr(user, "is_superuser", False):
            return

        user_uo = getattr(user, "unidade_orcamentaria", None)
        if user_uo is None or nova_uo != user_uo:
            raise DRFValidationError(
                {
                    "unidade_orcamentaria": "Você não pode cadastrar Unidade Administrativa em outra Unidade Orçamentária."  # noqa: E501
                }
            )

    def perform_create(self, serializer):
        self._validate_uo_scope(serializer.validated_data)
        with transaction.atomic():
            with audit_as(self.request.user):
                obj = serializer.save()
            self._audit_changes(obj, operation="create")

    def perform_update(self, serializer):
        original = UnidadeAdministrativa.objects.get(pk=serializer.instance.pk)
        self._validate_uo_scope(serializer.validated_data, instance=serializer.instance)

        with transaction.atomic():
            with audit_as(self.request.user):
                obj = serializer.save()
            self._audit_changes(obj, original=original, operation="update")

    def perform_destroy(self, instance):
        with transaction.atomic():
            try:
                self._audit_changes(instance, operation="delete")
                with audit_as(self.request.user):
                    instance.delete()
            except ProtectedError:
                raise DRFValidationError(
                    {
                        "detail": "Não foi possível excluir esta Unidade Administrativa porque existem vínculos ativos no sistema."
                    }
                )

    @extend_schema(
        tags=["Unidades Administrativas"],
        summary="Histórico da unidade administrativa",
        description="Retorna o histórico de alterações da unidade administrativa informada no ID.",
        parameters=[UA_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(
                response=UnidadeAdministrativaHistoricoGrupoSerializer(many=True),
                description="Histórico retornado com sucesso.",
            ),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para visualizar histórico."),
            404: OpenApiResponse(description="Unidade administrativa não encontrada."),
        },
    )
    @action(
        detail=True,
        methods=["get"],
        url_path="historico",
        filter_backends=[],
        pagination_class=None,
    )
    def historico(self, request, pk=None):
        return self._build_historico_response(self.get_object())

    @extend_schema(
        tags=["Unidades Administrativas"],
        summary="Exportar unidades administrativas",
        description="Exporta os dados filtrados para csv, xls, xlsx ou pdf.",
        parameters=[
            OpenApiParameter(
                name="formato",
                required=True,
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=["csv", "xls", "xlsx", "pdf"],
            )
        ],
        responses={
            200: OpenApiResponse(description="Arquivo de exportação gerado com sucesso."),
            400: OpenApiResponse(description="Parâmetros inválidos para exportação."),
            401: OpenApiResponse(description="Usuário não autenticado."),
            403: OpenApiResponse(description="Usuário sem permissão para exportar ou sem acesso ao escopo filtrado."),
        },
    )
    @action(detail=False, methods=["get"], url_path="exportar")
    def exportar(self, request):
        return self._build_export_response(request)
