from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models.deletion import ProtectedError

from django_filters.rest_framework import DjangoFilterBackend
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
        return bool(getattr(user, "is_gestor_patrimonio", False))

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

        if instance is not None and nova_uo is not None:
            if nova_uo != instance.unidade_orcamentaria:
                raise DRFValidationError(
                    {
                        "unidade_orcamentaria": (
                            "A Unidade Orçamentária não pode ser alterada."
                        )
                    }
                )

        if instance is not None and nova_uo is None:
            nova_uo = instance.unidade_orcamentaria

        if nova_uo is None:
            raise DRFValidationError(
                {"unidade_orcamentaria": "Unidade Orçamentária é obrigatória."}
            )

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
