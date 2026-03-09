from collections import defaultdict
from datetime import datetime

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse

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
    PermissionDenied,
    ValidationError as DRFValidationError,
)
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.response import Response

from dados_comuns.api_serializers import (
    UnidadeAdministrativaDetailSerializer,
    UnidadeAdministrativaExportQuerySerializer,
    UnidadeAdministrativaHistoricoGrupoSerializer,
    UnidadeAdministrativaListSerializer,
)
from dados_comuns.context import audit_as
from dados_comuns.formats import UnidadeAdministrativaPDFFormat
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa
from dados_comuns.permissions import UnidadeAdministrativaPermission
from dados_comuns.resources import UnidadeAdministrativaResource
from dados_comuns.utils import dict_changes


UA_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único da unidade administrativa.",
)


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
                name="unidade_orcamentaria",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Filtra por ID da Unidade Orçamentária. Retorna 403 quando o usuário não possui acesso ao escopo solicitado.",
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
class UnidadeAdministrativaViewSet(viewsets.ModelViewSet):
    permission_classes = [UnidadeAdministrativaPermission]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["status", "unidade_orcamentaria"]
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

    def get_serializer_class(self):
        if self.action == "list":
            return UnidadeAdministrativaListSerializer
        return UnidadeAdministrativaDetailSerializer

    def get_queryset(self):
        qs = UnidadeAdministrativa.objects.select_related("unidade_orcamentaria")

        user = self.request.user
        if getattr(user, "is_superuser", False):
            return qs

        uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if uo_id:
            return qs.filter(unidade_orcamentaria_id=uo_id)

        ua_id = getattr(user, "unidade_administrativa_id", None)
        if ua_id:
            return qs.filter(pk=ua_id)

        return qs.none()

    def get_object(self):
        obj = super().get_object()
        user = self.request.user

        if getattr(user, "is_superuser", False):
            return obj

        user_uo_id = getattr(user, "unidade_orcamentaria_id", None)
        user_ua_id = getattr(user, "unidade_administrativa_id", None)

        if user_uo_id:
            if obj.unidade_orcamentaria_id == user_uo_id:
                return obj
            raise NotFound()

        if user_ua_id:
            if obj.pk == user_ua_id:
                return obj
            raise NotFound()

        raise NotFound()

    def _uo_ids_permitidos(self, user):
        if getattr(user, "is_superuser", False):
            return None

        if getattr(user, "unidade_orcamentaria_id", None):
            return {user.unidade_orcamentaria_id}

        if getattr(user, "unidade_administrativa_id", None):
            uo_id = (
                UnidadeAdministrativa.objects.filter(pk=user.unidade_administrativa_id)
                .values_list("unidade_orcamentaria_id", flat=True)
                .first()
            )
            return {uo_id} if uo_id else set()

        return set()

    def _validar_filtro_unidade_orcamentaria(self):
        raw_uo = self.request.query_params.get("unidade_orcamentaria")
        if raw_uo in (None, ""):
            return

        try:
            requested_uo_id = int(raw_uo)
        except (TypeError, ValueError):
            return

        uo_ids_permitidos = self._uo_ids_permitidos(self.request.user)
        if uo_ids_permitidos is None:
            return

        if requested_uo_id not in uo_ids_permitidos:
            raise PermissionDenied(
                "Você não tem acesso à Unidade Orçamentária informada no filtro."
            )

    def list(self, request, *args, **kwargs):
        self._validar_filtro_unidade_orcamentaria()
        return super().list(request, *args, **kwargs)

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

    def _audit_changes(self, obj, original=None, operation="update"):
        ct = ContentType.objects.get_for_model(UnidadeAdministrativa)

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
        ua = self.get_object()

        ct = ContentType.objects.get_for_model(UnidadeAdministrativa)
        historicos = (
            HistoricoGeral.objects.filter(content_type=ct, object_id=str(ua.pk))
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

        serializer = UnidadeAdministrativaHistoricoGrupoSerializer(
            resposta_ordenada,
            many=True,
        )
        return Response(serializer.data)

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
        serializer = UnidadeAdministrativaExportQuerySerializer(
            data=request.query_params
        )
        serializer.is_valid(raise_exception=True)
        formato = serializer.validated_data["formato"]
        self._validar_filtro_unidade_orcamentaria()

        queryset = self.filter_queryset(self.get_queryset())
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"unidades_administrativas_{timestamp}.{formato}"

        if formato == "pdf":
            pdf_format = UnidadeAdministrativaPDFFormat()
            pdf_format._export_request = request
            pdf_format._export_queryset = queryset
            pdf_bytes = pdf_format.export_data(None)

            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        resource = UnidadeAdministrativaResource()
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
