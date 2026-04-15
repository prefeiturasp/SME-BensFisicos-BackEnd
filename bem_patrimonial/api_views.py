from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from datetime import datetime
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import BaixaFisicaBemPatrimonial, BaixaFisicaBensItem
from .api_serializers import (
    BaixaFisicaBemPatrimonialListSerializer,
    BaixaFisicaBemPatrimonialDetailSerializer,
    BaixaFisicaBemPatrimonialCreateSerializer,
    BaixaFisicaBemPatrimonialUpdateSerializer,
    BaixaFisicaEnviarSolicitacaoSerializer,
    BaixaFisicaAprovarSerializer,
    BaixaFisicaCancelarSerializer,
)
from .api_docs import (
    LIST_BAIXAS_FISICAS_DOC,
    CREATE_BAIXAS_FISICAS_DOC,
    RETRIEVE_BAIXAS_FISICAS_DOC,
    UPDATE_BAIXAS_FISICAS_DOC,
    DELETE_BAIXAS_FISICAS_DOC,
    ENVIAR_SOLICITACAO_DOC,
    APROVAR_BAIXA_FISICA_DOC,
    CANCELAR_BAIXA_FISICA_DOC,
    GERAR_NBBPM_DOC,
    EXPORTAR_EXCEL_DOC,
)
from .emails import (
    envia_email_baixa_fisica_solicitada,
    envia_email_baixa_fisica_aprovada,
    envia_email_baixa_fisica_cancelada,
)
from .nbbpm import http_response_nbbpm, gerar_numero_nbbpm
from . import constants
from dados_comuns.escopo import filtrar_queryset_por_escopo
from dados_comuns.context import set_user


class IsGestorPatrimonioOrOperadorInventario(IsAuthenticated):
    """
    Permissão customizada: usuário deve ser autenticado e ser
    gestor de patrimônio, operador de inventário ou superuser
    """

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        user = request.user
        return (
            user.is_gestor_patrimonio or
            user.is_operador_inventario or
            user.is_superuser
        )


class BaixaFisicaBemPatrimonialViewSet(viewsets.ModelViewSet):
    """
    ViewSet para Baixas Físicas de Bens Patrimoniais
    """

    permission_classes = [IsGestorPatrimonioOrOperadorInventario]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    filterset_fields = {
        'status': ['exact', 'in'],
        'unidade_administrativa_origem': ['exact'],
        'data_aprovacao': ['gte', 'lte', 'range'],
        'data_criacao': ['gte', 'lte', 'range'],
    }

    search_fields = [
        'numero_processo_baixa',
        'numero_nbbpm',
        'unidade_administrativa_origem__nome',
        'unidade_administrativa_origem__sigla',
        'criado_por__username',
        'criado_por__first_name',
        'criado_por__last_name',
        'itens__bem__numero_patrimonial',
        'itens__bem__nome',
    ]

    ordering_fields = [
        'id',
        'data_criacao',
        'data_aprovacao',
        'status',
        'numero_nbbpm',
    ]
    ordering = ['-data_criacao']

    def get_queryset(self):
        queryset = BaixaFisicaBemPatrimonial.objects.all()
        queryset = filtrar_queryset_por_escopo(
            usuario=self.request.user,
            queryset=queryset,
            campo_ua='unidade_administrativa_origem'
        )
        queryset = queryset.select_related(
            'unidade_administrativa_origem',
            'criado_por',
            'aprovado_por'
        ).prefetch_related('itens__bem')
        return queryset.distinct()

    def get_serializer_class(self):
        if self.action == 'list':
            return BaixaFisicaBemPatrimonialListSerializer
        elif self.action == 'retrieve':
            return BaixaFisicaBemPatrimonialDetailSerializer
        elif self.action == 'create':
            return BaixaFisicaBemPatrimonialCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return BaixaFisicaBemPatrimonialUpdateSerializer
        elif self.action == 'enviar_solicitacao':
            return BaixaFisicaEnviarSolicitacaoSerializer
        elif self.action == 'aprovar':
            return BaixaFisicaAprovarSerializer
        elif self.action == 'cancelar':
            return BaixaFisicaCancelarSerializer
        return BaixaFisicaBemPatrimonialDetailSerializer

    def _detail_response(self, baixa, request, http_status=status.HTTP_200_OK):
        """Retorna resposta com o serializer de detalhe."""
        return Response(
            BaixaFisicaBemPatrimonialDetailSerializer(
                baixa, context={'request': request}
            ).data,
            status=http_status,
        )

    # =========================================================
    # LIST
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Listar baixas físicas",
        description=LIST_BAIXAS_FISICAS_DOC,
        responses={200: BaixaFisicaBemPatrimonialListSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # =========================================================
    # CREATE
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Criar baixa física",
        description=CREATE_BAIXAS_FISICAS_DOC,
        responses={
            201: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
        },
    )
    def create(self, request, *args, **kwargs):
        # CORRIGIDO: popula contexto de auditoria antes do serializer salvar
        # bens (bem.save() aciona _registrar_auditoria_se_alterado via get_user())
        set_user(request.user)
        return super().create(request, *args, **kwargs)

    # =========================================================
    # RETRIEVE
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Detalhar baixa física",
        description=RETRIEVE_BAIXAS_FISICAS_DOC,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    # =========================================================
    # UPDATE / PARTIAL UPDATE
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Atualizar baixa física",
        description=UPDATE_BAIXAS_FISICAS_DOC,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    def update(self, request, *args, **kwargs):
        # CORRIGIDO: popula contexto de auditoria antes de salvar bens
        set_user(request.user)
        return super().update(request, *args, **kwargs)

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Atualização parcial",
        description=UPDATE_BAIXAS_FISICAS_DOC,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
        },
    )
    def partial_update(self, request, *args, **kwargs):
        # CORRIGIDO: popula contexto de auditoria antes de salvar bens
        set_user(request.user)
        return super().partial_update(request, *args, **kwargs)

    # =========================================================
    # ENVIAR SOLICITAÇÃO
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Enviar solicitação",
        description=ENVIAR_SOLICITACAO_DOC,
        request=None,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    @action(detail=True, methods=['post'], url_path='enviar-solicitacao')
    def enviar_solicitacao(self, request, pk=None):
        baixa = self.get_object()

        serializer = self.get_serializer(
            data={}, context={'baixa': baixa, 'request': request}
        )
        serializer.is_valid(raise_exception=True)

        set_user(request.user)
        baixa.enviar_solicitacao()

        try:
            envia_email_baixa_fisica_solicitada(baixa)
        except Exception:
            pass

        return self._detail_response(baixa, request)

    # =========================================================
    # APROVAR
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Aprovar baixa física",
        description=APROVAR_BAIXA_FISICA_DOC,
        request=None,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            403: OpenApiResponse(description="Sem permissão"),
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    @action(detail=True, methods=['post'])
    def aprovar(self, request, pk=None):
        baixa = self.get_object()

        serializer = self.get_serializer(
            data={}, context={'baixa': baixa, 'request': request}
        )
        serializer.is_valid(raise_exception=True)

        set_user(request.user)
        baixa.aprovar(usuario_aprovador=request.user)

        if not baixa.numero_nbbpm:
            baixa.numero_nbbpm = gerar_numero_nbbpm(baixa)
            baixa.save(update_fields=['numero_nbbpm'])

        try:
            envia_email_baixa_fisica_aprovada(baixa)
        except Exception:
            pass

        return self._detail_response(baixa, request)

    # =========================================================
    # CANCELAR
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Cancelar baixa física",
        description=CANCELAR_BAIXA_FISICA_DOC,
        request=BaixaFisicaCancelarSerializer,
        responses={
            200: BaixaFisicaBemPatrimonialDetailSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            403: OpenApiResponse(description="Sem permissão"),
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    @action(detail=True, methods=['post'])
    def cancelar(self, request, pk=None):
        baixa = self.get_object()

        serializer = self.get_serializer(
            data=request.data, context={'baixa': baixa, 'request': request}
        )
        serializer.is_valid(raise_exception=True)

        set_user(request.user)
        self._restaurar_bens_da_baixa(baixa)

        baixa.status = constants.RECUSADA
        baixa.save(update_fields=['status'])

        try:
            envia_email_baixa_fisica_cancelada(baixa, request.user)
        except Exception:
            pass

        return self._detail_response(baixa, request)

    def _restaurar_bens_da_baixa(self, baixa: BaixaFisicaBemPatrimonial) -> None:
        """Restaura o status dos bens ao cancelar uma baixa."""
        for item in baixa.itens.select_related('bem'):
            bem = item.bem
            if bem.status == constants.BAIXA_FISICA_AGUARDANDO_APROVACAO:
                bem.status = constants.APROVADO
                bem.save(update_fields=['status'])

    # =========================================================
    # GERAR NBBPM
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Gerar PDF NBBPM",
        description=GERAR_NBBPM_DOC,
        request=None,
        responses={
            200: OpenApiResponse(description="PDF da Nota NBBPM"),
            400: OpenApiResponse(description="Baixa não aprovada ou sem NBBPM"),
            404: OpenApiResponse(description="Baixa física não encontrada"),
        },
    )
    @action(detail=True, methods=['get'], url_path='gerar-nbbpm')
    def gerar_nbbpm(self, request, pk=None):
        baixa = self.get_object()

        if baixa.status != constants.ACEITA:
            return Response(
                {'detail': 'A Nota NBBPM só pode ser gerada para baixas aprovadas.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not baixa.numero_nbbpm:
            return Response(
                {'detail': 'Esta baixa não possui número NBBPM.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        return http_response_nbbpm(baixa)

    # =========================================================
    # EXPORTAR EXCEL
    # =========================================================

    @extend_schema(
        tags=["Baixas Físicas"],
        summary="Exportar para Excel",
        description=EXPORTAR_EXCEL_DOC,
        request=None,
        responses={200: OpenApiResponse(description="Arquivo Excel")},
    )
    @action(detail=False, methods=['get'], url_path='exportar-excel')
    def exportar_excel(self, request):
        queryset = self._get_queryset_para_exportacao(request)
        wb = self._construir_workbook(queryset)
        return self._montar_resposta_excel(wb)

    def _get_queryset_para_exportacao(self, request):
        """Aplica filtros e restrição por IDs ao queryset de exportação."""
        queryset = self.filter_queryset(self.get_queryset())
        ids_param = request.query_params.get('ids')
        if ids_param:
            ids_list = self._parse_ids(ids_param)
            if ids_list:
                queryset = queryset.filter(id__in=ids_list)
        return queryset

    def _parse_ids(self, ids_param: str) -> list:
        """Converte string de IDs separados por vírgula em lista de ints."""
        ids = []
        for id_str in ids_param.split(','):
            try:
                ids.append(int(id_str.strip()))
            except (ValueError, TypeError):
                pass
        return ids

    def _construir_workbook(self, queryset) -> Workbook:
        """Monta o workbook Excel com cabeçalho e dados."""
        wb = Workbook()
        ws = wb.active
        ws.title = "Baixas Físicas"
        self._escrever_cabecalho(ws)
        self._escrever_dados(ws, queryset)
        self._ajustar_colunas(ws)
        return wb

    def _escrever_cabecalho(self, ws) -> None:
        headers = [
            'Unidade Administrativa', 'Número Patrimonial', 'Nome do Bem',
            'Status', 'NBBPM', 'Usuário que solicitou a Baixa',
            'Gestor que aprovou a solicitação', 'Data da Aprovação',
        ]
        header_fill = PatternFill(start_color="2E7D32", end_color="2E7D32", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        for col_num, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_num)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = header_alignment

    def _escrever_dados(self, ws, queryset) -> None:
        row_num = 2
        for baixa in queryset:
            itens_baixa = list(baixa.itens.all())
            if not itens_baixa:
                self._escrever_linha(ws, row_num, baixa, bem=None)
                row_num += 1
            else:
                for item in itens_baixa:
                    self._escrever_linha(ws, row_num, baixa, bem=item.bem)
                    row_num += 1

        cell_alignment = Alignment(vertical='center', wrap_text=True)
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            for cell in row:
                cell.alignment = cell_alignment

    def _escrever_linha(self, ws, row_num: int, baixa, bem) -> None:
        data_aprovacao = (
            baixa.data_aprovacao.strftime('%d/%m/%Y %H:%M')
            if baixa.data_aprovacao else '-'
        )
        ws.cell(row=row_num, column=1).value = str(
            baixa.unidade_administrativa_origem) if baixa.unidade_administrativa_origem else '-'
        ws.cell(row=row_num, column=2).value = bem.numero_patrimonial if bem else '-'
        ws.cell(row=row_num, column=3).value = bem.nome if bem else '-'
        ws.cell(row=row_num, column=4).value = baixa.get_status_display()
        ws.cell(row=row_num, column=5).value = baixa.numero_nbbpm or '-'
        ws.cell(row=row_num, column=6).value = str(baixa.criado_por) if baixa.criado_por else '-'
        ws.cell(row=row_num, column=7).value = str(baixa.aprovado_por) if baixa.aprovado_por else '-'
        ws.cell(row=row_num, column=8).value = data_aprovacao

    def _ajustar_colunas(self, ws) -> None:
        for i, width in enumerate([30, 20, 35, 20, 20, 30, 30, 20], 1):
            ws.column_dimensions[get_column_letter(i)].width = width

    def _montar_resposta_excel(self, wb: Workbook) -> HttpResponse:
        response = HttpResponse(
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        filename = f'baixas_fisicas_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        wb.save(response)
        return response
