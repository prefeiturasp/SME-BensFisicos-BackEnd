from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models.deletion import ProtectedError

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, ValidationError as DRFValidationError
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import BasePermission

from inventario.api_serializers import (
    ParametroConciliacaoAnualDetailSerializer,
    ParametroConciliacaoAnualListSerializer,
)
from inventario.models import ParametroConciliacaoAnual


class ParametroConciliacaoAnualPermission(BasePermission):
    def _pode_acessar_modulo(self, user):
        if not user or not user.is_authenticated:
            return False
        if getattr(user, "is_superuser", False):
            return True
        return bool(
            getattr(user, "is_gestor_patrimonio", False)
            or getattr(user, "is_operador_inventario", False)
        )

    def _pode_gerenciar(self, user):
        return bool(
            getattr(user, "is_superuser", False)
            or getattr(user, "is_gestor_patrimonio", False)
        )

    def has_permission(self, request, view):
        if not self._pode_acessar_modulo(request.user):
            return False

        action = getattr(view, "action", None)
        if action in ("list", "retrieve"):
            return True

        if action in ("create", "update", "partial_update", "destroy"):
            return self._pode_gerenciar(request.user)

        return self._pode_gerenciar(request.user)

    def has_object_permission(self, request, view, obj):
        action = getattr(view, "action", None)
        if action == "retrieve":
            return True

        if action in ("update", "partial_update", "destroy"):
            return self._pode_gerenciar(request.user)

        return True


PARAMETRO_ID_PATH_PARAM = OpenApiParameter(
    name="id",
    required=True,
    type=OpenApiTypes.INT,
    location=OpenApiParameter.PATH,
    description="Identificador numérico único do parâmetro de conciliação anual.",
)

PARAMETRO_TAG = "Parâmetros de Conciliação Anual"
PARAMETRO_NAO_ENCONTRADO = "Parâmetro de conciliação anual não encontrado."
UNAUTHORIZED_RESPONSE = OpenApiResponse(description="Usuário não autenticado.")
INVALID_DATA_RESPONSE = OpenApiResponse(description="Dados inválidos.")


def forbidden_response(action):
    return OpenApiResponse(description=f"Usuário sem permissão para {action}.")


def not_found_response():
    return OpenApiResponse(description=PARAMETRO_NAO_ENCONTRADO)


def write_responses(success_status, success_description, action):
    return {
        success_status: OpenApiResponse(description=success_description),
        400: INVALID_DATA_RESPONSE,
        401: UNAUTHORIZED_RESPONSE,
        403: forbidden_response(action),
        404: not_found_response(),
    }


@extend_schema_view(
    list=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Listar parâmetros de conciliação anual",
        description="Lista paginada com busca, filtros e ordenação.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description=(
                    "Busca em: ano_referencia, unidade_orcamentaria__codigo, "
                    "unidade_orcamentaria__sigla e unidade_orcamentaria__nome."
                ),
            ),
            OpenApiParameter(
                name="ordering",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description=(
                    "Ordenação por: id, ano_referencia, periodo_inicial, "
                    "periodo_final, ativo e unidade_orcamentaria__codigo. "
                    "Use '-' para descendente."
                ),
            ),
            OpenApiParameter(
                name="ativo",
                type=OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Filtra por parâmetros ativos/inativos.",
            ),
            OpenApiParameter(
                name="ano_referencia",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Filtra pelo ano de referência.",
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
            401: UNAUTHORIZED_RESPONSE,
            403: forbidden_response("acessar o recurso"),
        },
    ),
    retrieve=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Detalhar parâmetro de conciliação anual",
        parameters=[PARAMETRO_ID_PATH_PARAM],
        responses={
            200: OpenApiResponse(description="Detalhe retornado com sucesso."),
            401: UNAUTHORIZED_RESPONSE,
            403: forbidden_response("acessar o recurso"),
            404: not_found_response(),
        },
    ),
    create=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Criar parâmetro de conciliação anual",
        responses=write_responses(201, "Parâmetro criado com sucesso.", "criar"),
    ),
    update=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Atualizar parâmetro de conciliação anual",
        parameters=[PARAMETRO_ID_PATH_PARAM],
        responses=write_responses(200, "Parâmetro atualizado com sucesso.", "atualizar"),
    ),
    partial_update=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Atualizar parcialmente parâmetro de conciliação anual",
        parameters=[PARAMETRO_ID_PATH_PARAM],
        responses=write_responses(200, "Parâmetro atualizado com sucesso.", "atualizar"),
    ),
    destroy=extend_schema(
        tags=[PARAMETRO_TAG],
        summary="Excluir parâmetro de conciliação anual",
        parameters=[PARAMETRO_ID_PATH_PARAM],
        responses={
            204: OpenApiResponse(description="Parâmetro excluído com sucesso."),
            400: OpenApiResponse(
                description="Não foi possível excluir por regra de integridade."
            ),
            401: UNAUTHORIZED_RESPONSE,
            403: forbidden_response("excluir"),
            404: not_found_response(),
        },
    ),
)
class ParametroConciliacaoAnualViewSet(viewsets.ModelViewSet):
    permission_classes = [ParametroConciliacaoAnualPermission]

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["ativo", "ano_referencia"]
    search_fields = [
        "ano_referencia",
        "unidade_orcamentaria__codigo",
        "unidade_orcamentaria__sigla",
        "unidade_orcamentaria__nome",
    ]
    ordering_fields = [
        "id",
        "ano_referencia",
        "periodo_inicial",
        "periodo_final",
        "ativo",
        "unidade_orcamentaria__codigo",
    ]
    ordering = ["-ano_referencia", "-periodo_inicial", "unidade_orcamentaria__codigo"]

    def get_serializer_class(self):
        if self.action == "list":
            return ParametroConciliacaoAnualListSerializer
        return ParametroConciliacaoAnualDetailSerializer

    def get_queryset(self):
        qs = ParametroConciliacaoAnual.objects.select_related("unidade_orcamentaria")

        user = self.request.user
        uo_id = getattr(user, "unidade_orcamentaria_id", None)
        if uo_id:
            return qs.filter(unidade_orcamentaria_id=uo_id)

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
                    "unidade_orcamentaria": (
                        "Você não pode gerenciar parâmetros de outra "
                        "Unidade Orçamentária."
                    )
                }
            )

    def _raise_drf_validation_error(self, exc):
        if hasattr(exc, "message_dict"):
            errors = dict(exc.message_dict)
            if "__all__" in errors:
                errors["non_field_errors"] = errors.pop("__all__")
            raise DRFValidationError(errors)

        if hasattr(exc, "messages"):
            raise DRFValidationError({"non_field_errors": exc.messages})

        raise DRFValidationError({"non_field_errors": [str(exc)]})

    def perform_create(self, serializer):
        self._validate_uo_scope(serializer.validated_data)
        try:
            serializer.save()
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

    def perform_update(self, serializer):
        self._validate_uo_scope(
            serializer.validated_data,
            instance=serializer.instance,
        )
        try:
            serializer.save()
        except DjangoValidationError as exc:
            self._raise_drf_validation_error(exc)

    def perform_destroy(self, instance):
        try:
            instance.delete()
        except ProtectedError:
            raise DRFValidationError(
                {
                    "detail": (
                        "Não foi possível excluir este parâmetro porque "
                        "existem vínculos ativos no sistema."
                    )
                }
            )
