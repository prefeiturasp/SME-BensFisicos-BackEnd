from rest_framework import viewsets, status, filters, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
import django_filters

from bem_patrimonial.models import NBBPM
from bem_patrimonial.api_serializers import NBBPMSerializer, NBBPMGerarLoteSerializer
from bem_patrimonial.nbbpm_lote import http_response_nbbpm_lote
from bem_patrimonial.services.nbbpm_numero import criar_nbbpm_com_retry
from dados_comuns.escopo import resolver_ids_escopo

from drf_spectacular.utils import extend_schema, OpenApiResponse


class IsGestorPatrimonioOrSuperUser(IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        user = request.user
        return bool(getattr(user, "is_gestor_patrimonio", False) or getattr(user, "is_superuser", False))


class NBBPMFilter(django_filters.FilterSet):
    numero = django_filters.CharFilter(field_name="numero", lookup_expr="icontains")
    data_autorizacao__gte = django_filters.DateFilter(field_name="data_autorizacao", lookup_expr="gte")
    data_autorizacao__lte = django_filters.DateFilter(field_name="data_autorizacao", lookup_expr="lte")
    responsavel = django_filters.CharFilter(field_name="responsavel", lookup_expr="icontains")

    class Meta:
        model = NBBPM
        fields = []


class NBBPMViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """NBBPM: listar, criar lote e PDF (escopo por UO/UA)."""

    permission_classes = [IsGestorPatrimonioOrSuperUser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = NBBPMFilter

    search_fields = (
        "numero",
        "numero_processo_baixa",
        "responsavel",
        "baixas__numero_processo_baixa",
        "baixas__unidade_administrativa_origem__nome",
        "baixas__unidade_administrativa_origem__sigla",
    )
    ordering_fields = ["id", "data_criacao", "data_autorizacao", "numero"]
    ordering = ["-data_criacao"]

    def get_queryset(self):
        qs = NBBPM.objects.all().select_related("criado_por").prefetch_related(
            "baixas__unidade_administrativa_origem__unidade_orcamentaria",
            "baixas__itens__bem",
        )

        user = self.request.user
        _, is_gestor, ua_id, uo_id = resolver_ids_escopo(user)

        if ua_id:
            return qs.filter(baixas__unidade_administrativa_origem_id=ua_id).distinct()

        if is_gestor and uo_id:
            return qs.filter(
                baixas__unidade_administrativa_origem__unidade_orcamentaria_id=uo_id
            ).distinct()

        return qs.none()

    def get_serializer_class(self):
        if self.action == "create":
            return NBBPMGerarLoteSerializer
        return NBBPMSerializer

    @extend_schema(
        tags=["NBBPM"],
        summary="Listar NBBPMs",
        description="Lista NBBPMs filtradas por escopo M2M (UO/UA) com suporte a filtros.",
        responses={200: NBBPMSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["NBBPM"],
        summary="Criar NBBPM consolidada",
        description="Gera NBBPM consolidada via serviço unificado (prefixo fixo 001, sequencial global por ano).",
        request=NBBPMGerarLoteSerializer,
        responses={201: NBBPMSerializer},
    )
    def create(self, request, *args, **kwargs):
        serializer = NBBPMGerarLoteSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not (getattr(user, "is_gestor_patrimonio", False) or getattr(user, "is_superuser", False)):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("Apenas Gestor de Patrimônio pode gerar NBBPM.")

        validated = serializer.validated_data
        baixas = validated.pop("baixas")

        nbbpm = criar_nbbpm_com_retry(
            baixas=baixas,
            criado_por=user,
            **validated,
        )

        out = NBBPMSerializer(nbbpm, context={"request": request})
        return Response(out.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=["NBBPM"],
        summary="Detalhar NBBPM",
        responses={200: NBBPMSerializer},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["NBBPM"],
        summary="Gerar PDF NBBPM",
        description="Gera PDF no layout lote (6 colunas DE/ATÉ)",
        responses={200: OpenApiResponse(description="PDF da NBBPM")},
    )
    @action(detail=True, methods=["get"], url_path="pdf")
    def pdf(self, request, pk=None):
        nbbpm = self.get_object()
        return http_response_nbbpm_lote(nbbpm, usuario_gerador=request.user)
