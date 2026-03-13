from django.contrib.auth import get_user_model
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetView,
    PasswordResetConfirmView,
)
from dados_comuns.permissions import UsuarioPermission
from dados_comuns.libs.pagination import SafePagination
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.exceptions import NotFound, PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.tokens import default_token_generator
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy, reverse
from urllib.parse import urlencode
from django.utils import timezone
from django.views.generic import TemplateView
from dados_comuns.models import HistoricoGeral, UnidadeAdministrativa
from dados_comuns.utils import dict_changes
import logging
from django.contrib.auth import get_user_model
from rest_framework import viewsets, mixins, status
from rest_framework.permissions import IsAdminUser
from usuario.serializers import UsuarioSerializer
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from usuario.filters import UsuarioFilter
from rest_framework.decorators import action
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
)
from usuario.api_doc import *

logger = logging.getLogger(__name__)
User = get_user_model()


class AdminLoginView(LoginView):
    template_name = "admin/login.html"

    def get_success_url(self):
        next_url = self.request.POST.get("next") or self.request.GET.get("next")
        if next_url:
            return f"{reverse('selecionar_ua')}?{urlencode({'next': next_url})}"
        return reverse("selecionar_ua")


class LoginPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    template_name = "admin/password_change.html"
    success_url = reverse_lazy("password_change_done")
    form_class = SetPasswordForm

    def dispatch(self, request, *args, **kwargs):
        user_id = request.GET.get("user_id") or request.POST.get("user_id")
        if user_id and request.user.is_staff:
            self.user_to_change = get_object_or_404(User, pk=user_id)
        else:
            self.user_to_change = request.user
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.user_to_change
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_id"] = (
            self.request.GET.get("user_id")
            or self.request.POST.get("user_id")
            or (self.user_to_change.pk if self.user_to_change else None)
        )
        ctx["next"] = self.request.GET.get("next") or self.request.POST.get("next")
        return ctx

    def form_valid(self, form):
        resp = super().form_valid(form)
        updates = []
        if (
            hasattr(self.user_to_change, "must_change_password")
            and self.user_to_change.must_change_password
        ):
            self.user_to_change.must_change_password = False
            updates.append("must_change_password")
        if hasattr(self.user_to_change, "last_password_change"):
            self.user_to_change.last_password_change = timezone.now()
            updates.append("last_password_change")
        if updates:
            self.user_to_change.save(update_fields=updates)
        return resp

    def get_success_url(self):
        nxt = self.request.POST.get("next") or self.request.GET.get("next")
        return nxt or super().get_success_url()


class LoginPasswordChangeDoneView(LoginRequiredMixin, TemplateView):
    template_name = "admin/password_change_done.html"


class PasswordRecoveryRequestView(PasswordResetView):

    template_name = "admin/password_recovery_request.html"
    email_template_name = "admin/password_recovery_email.html"
    success_url = reverse_lazy("password_recovery_done")
    token_generator = default_token_generator
    from_email = None
    html_email_template_name = "admin/password_recovery_email.html"
    subject = "[Bens Físicos] Recuperação de senha solicitada"

    def get_users(self, email):
        active_users = User.objects.filter(email__iexact=email, is_active=True)
        return (u for u in active_users if u.has_usable_password())

    def form_valid(self, form):
        email = form.cleaned_data["email"]
        logger.info(f"Solicitação de recuperação de senha para {email}")
        return super().form_valid(form)


class PasswordRecoveryDoneView(TemplateView):

    template_name = "admin/password_recovery_done.html"


class PasswordRecoveryConfirmView(PasswordResetConfirmView):

    template_name = "admin/password_recovery_confirm.html"
    success_url = reverse_lazy("password_recovery_complete")
    token_generator = default_token_generator

    def form_valid(self, form):
        user = form.save()

        updates = []
        if hasattr(user, "must_change_password"):
            user.must_change_password = False
            updates.append("must_change_password")
        if hasattr(user, "last_password_change"):
            user.last_password_change = timezone.now()
            updates.append("last_password_change")

        if updates:
            user.save(update_fields=updates)

        logger.info(f"Senha recuperada com sucesso para usuário {user.username}")
        return super().form_valid(form)


class PasswordRecoveryCompleteView(TemplateView):

    template_name = "admin/password_recovery_complete.html"


class SelecionarUAView(LoginRequiredMixin, TemplateView):
    template_name = "admin/selecionar_ua.html"
    login_url = "/admin/login/"
    VISAO_GERAL_VALUE = "__UO__"

    def _obter_uo_ativa(self, user):
        if user.unidade_orcamentaria_id:
            return user.unidade_orcamentaria
        if user.unidade_administrativa_id and user.unidade_administrativa:
            return user.unidade_administrativa.unidade_orcamentaria
        return None

    def get_uas_disponiveis(self):
        user = self.request.user
        if user.is_superuser:
            return UnidadeAdministrativa.objects.filter(
                status=UnidadeAdministrativa.ATIVA
            ).select_related("unidade_orcamentaria")
        if user.is_gestor_patrimonio:
            uo_id = user.unidade_orcamentaria_id
            if uo_id:
                return UnidadeAdministrativa.objects.filter(
                    unidade_orcamentaria_id=uo_id,
                    status=UnidadeAdministrativa.ATIVA,
                ).select_related("unidade_orcamentaria")
        return user.unidades_administrativas.filter(
            status=UnidadeAdministrativa.ATIVA
        ).select_related("unidade_orcamentaria")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        uo_ativa = self._obter_uo_ativa(user)
        permite_visao_geral = bool(user.is_superuser or user.is_gestor_patrimonio)

        ctx["uas_disponiveis"] = self.get_uas_disponiveis()
        ctx["ua_ativa_id"] = user.unidade_administrativa_id
        ctx["uo_ativa"] = uo_ativa
        ctx["permite_visao_geral"] = permite_visao_geral and bool(uo_ativa)
        ctx["visao_geral_value"] = self.VISAO_GERAL_VALUE
        ctx["visao_geral_selected"] = (
            permite_visao_geral and not user.unidade_administrativa_id
        )
        ctx["next"] = self.request.GET.get("next", reverse("admin:index"))
        ctx["error"] = None
        return ctx

    def _save_user_ua_uo_historico(self, user, update_fields):
        from usuario.models import Usuario

        original = Usuario.objects.get(pk=user.pk)
        with transaction.atomic():
            if update_fields:
                user.save(update_fields=update_fields)
                changes = dict_changes(
                    original,
                    user,
                    fields=["unidade_administrativa", "unidade_orcamentaria"],
                )
                if changes:
                    ct = ContentType.objects.get_for_model(Usuario)
                    HistoricoGeral.objects.bulk_create(
                        [
                            HistoricoGeral(
                                content_type=ct,
                                object_id=str(user.pk),
                                campo=field,
                                valor_antigo=old,
                                valor_novo=new,
                                alterado_por=user,
                            )
                            for field, (old, new) in changes.items()
                        ]
                    )

    def _post_visao_geral(self, request, next_url):
        user = request.user
        if not (user.is_superuser or user.is_gestor_patrimonio):
            ctx = self.get_context_data()
            ctx["error"] = (
                "A visão geral da UO é permitida apenas para gestor e superusuário."
            )
            return self.render_to_response(ctx)
        uo_ativa = self._obter_uo_ativa(user)
        if not uo_ativa:
            ctx = self.get_context_data()
            ctx["error"] = (
                "Não foi possível identificar a Unidade Orçamentária para visão geral."
            )
            return self.render_to_response(ctx)
        if not uo_ativa.ativa:
            ctx = self.get_context_data()
            ctx["error"] = "A Unidade Orçamentária vinculada está inativa."
            return self.render_to_response(ctx)
        update_fields = []
        if user.unidade_administrativa_id is not None:
            user.unidade_administrativa = None
            update_fields.append("unidade_administrativa")
        if user.unidade_orcamentaria_id != uo_ativa.id:
            user.unidade_orcamentaria = uo_ativa
            update_fields.append("unidade_orcamentaria")
        self._save_user_ua_uo_historico(user, update_fields)
        return redirect(next_url)

    def _post_ua_especifica(self, request, ua_id, next_url):
        user = request.user
        uas_disponiveis = self.get_uas_disponiveis()
        if not uas_disponiveis.filter(id=ua_id).exists():
            ctx = self.get_context_data()
            ctx["error"] = (
                "Você não tem permissão para acessar essa Unidade Administrativa."
            )
            return self.render_to_response(ctx)
        ua = UnidadeAdministrativa.objects.get(id=ua_id)
        update_fields = []
        if user.unidade_administrativa_id != ua.id:
            user.unidade_administrativa = ua
            update_fields.append("unidade_administrativa")
        if (
            ua.unidade_orcamentaria_id
            and user.unidade_orcamentaria_id != ua.unidade_orcamentaria_id
        ):
            user.unidade_orcamentaria = ua.unidade_orcamentaria
            update_fields.append("unidade_orcamentaria")
        self._save_user_ua_uo_historico(user, update_fields)
        return redirect(next_url)

    def post(self, request, *args, **kwargs):
        ua_id = request.POST.get("unidade_administrativa")
        next_url = request.POST.get("next", reverse("admin:index"))

        if ua_id == self.VISAO_GERAL_VALUE:
            return self._post_visao_geral(request, next_url)

        if not ua_id:
            ctx = self.get_context_data()
            ctx["error"] = "Selecione uma Unidade Administrativa."
            return self.render_to_response(ctx)

        try:
            ua_id = int(ua_id)
        except (ValueError, TypeError):
            ctx = self.get_context_data()
            ctx["error"] = "Unidade Administrativa inválida."
            return self.render_to_response(ctx)

        return self._post_ua_especifica(request, ua_id, next_url)


class UsuarioViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """
    CRUD completo de usuários com controle explícito
    """

    serializer_class = UsuarioSerializer
    permission_classes = [UsuarioPermission]
    pagination_class = SafePagination

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    filterset_class = UsuarioFilter

    search_fields = [
        "username",
        "nome",
        "email",
        "rf",
    ]

    ordering_fields = [
        "id",
        "username",
        "nome",
        "email",
        "rf",
        "is_active",
        "last_login",
        "date_joined",
    ]

    ordering = ["nome"]

    # =========================================================
    # QUERYSET COM ESCOPOS
    # =========================================================

    def get_queryset(self):
        qs = User.objects.select_related(
            "unidade_orcamentaria",
            "unidade_administrativa"
        ).prefetch_related("groups")

        user = self.request.user

        # superuser vê tudo
        if getattr(user, "is_superuser", False):
            return qs

        # operador não tem acesso
        if getattr(user, "is_operador_inventario", False):
            return qs.none()

        # gestor vê apenas usuários da mesma UO
        if getattr(user, "unidade_orcamentaria_id", None):
            return qs.filter(
                unidade_orcamentaria_id=user.unidade_orcamentaria_id
            )

        return qs.none()

    # =========================================================
    # OBJECT COM ESCOPOS
    # =========================================================

    def get_object(self):
        obj = super().get_object()
        user = self.request.user

        # superuser pode acessar qualquer
        if getattr(user, "is_superuser", False):
            return obj

        # operador não acessa usuários
        if getattr(user, "is_operador_inventario", False):
            raise PermissionDenied(
                "Operadores não possuem acesso ao gerenciamento de usuários."
            )

        # gestor só acessa usuários da mesma UO
        user_uo = getattr(user, "unidade_orcamentaria_id", None)

        if user_uo and obj.unidade_orcamentaria_id == user_uo:
            return obj

        raise NotFound()

    # =========================================================
    # HISTÓRICO
    # =========================================================

    def _registrar_historico(self, request, original, instance, fields):
        """
        Registra alterações no HistoricoGeral
        """
        changes = dict_changes(original, instance, fields=fields)

        if not changes:
            return

        ct = ContentType.objects.get_for_model(instance.__class__)

        HistoricoGeral.objects.bulk_create(
            [
                HistoricoGeral(
                    content_type=ct,
                    object_id=str(instance.pk),
                    campo=field,
                    valor_antigo=old,
                    valor_novo=new,
                    alterado_por=request.user,
                )
                for field, (old, new) in changes.items()
            ]
        )

    # =========================================================
    # LIST
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Listar usuários",
        description=LIST_USERS_DOC,
        responses={200: UsuarioSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # =========================================================
    # CREATE
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Criar usuário",
        description=CREATE_USERS_DOC,
        responses={
            201: UsuarioSerializer,
            400: OpenApiResponse(description="Erro de validação"),
        },
    )
    def create(self, request, *args, **kwargs):

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        user.must_change_password = True
        user.last_password_change = timezone.now()
        user.save(update_fields=["must_change_password", "last_password_change"])

        ct = ContentType.objects.get_for_model(User)

        HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(user.pk),
            campo="",
            valor_antigo="",
            valor_novo="",
            alterado_por=request.user,
            justificativa="Usuário criado"
        )

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # =========================================================
    # RETRIEVE
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Detalhar usuário",
        description=RETRIEVE_USERS_DOC,
        responses={
            200: UsuarioSerializer,
            404: OpenApiResponse(description="Usuário não encontrado"),
        },
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    # =========================================================
    # UPDATE
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Atualizar usuário",
        description=UPDATE_USERS_DOC,
        responses={
            200: UsuarioSerializer,
            400: OpenApiResponse(description="Erro de validação"),
            404: OpenApiResponse(description="Usuário não encontrado"),
        },
    )
    def update(self, request, *args, **kwargs):

        partial = kwargs.pop("partial", False)

        instance = self.get_object()

        original = User.objects.get(pk=instance.pk)

        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial
        )

        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        if "password" in request.data:
            user.last_password_change = timezone.now()
            user.save(update_fields=["last_password_change"])

        self._registrar_historico(
            request,
            original,
            user,
            fields=[
                "username",
                "email",
                "nome",
                "rf",
                "is_active",
                "is_staff",
                "is_superuser",
                "unidade_orcamentaria",
                "unidade_administrativa",
            ],
        )

        return Response(serializer.data)

    # =========================================================
    # PARTIAL UPDATE
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Atualização parcial",
        description=PATCH_USERS_DOC,
        responses={
            200: UsuarioSerializer,
            400: OpenApiResponse(description="Erro de validação"),
        },
    )
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    # =========================================================
    # DELETE (SOFT DELETE)
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Desativar usuário",
        description=DELETE_USERS_DOC,
        responses={
            200: OpenApiResponse(description="Usuário desativado com sucesso"),
            400: OpenApiResponse(description="Operação inválida"),
            404: OpenApiResponse(description="Usuário não encontrado"),
        },
    )
    def destroy(self, request, *args, **kwargs):

        instance = self.get_object()

        if instance.is_superuser:
            return Response(
                {"detail": "Não é permitido remover superusuário."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not instance.is_active:
            return Response(
                {"detail": "Usuário já está desativado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ct = ContentType.objects.get_for_model(User)

        HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(instance.pk),
            campo="is_active",
            valor_antigo="True",
            valor_novo="False",
            alterado_por=request.user,
            justificativa="Usuário Desativado",
        )

        instance.is_active = False
        instance.save(update_fields=["is_active"])

        return Response(
            {"detail": "Usuário desativado com sucesso."},
            status=status.HTTP_200_OK,
        )

    # =========================================================
    # RESTORE
    # =========================================================

    @extend_schema(
        tags=["Usuários"],
        summary="Reativar usuário",
        description=RESTORE_USERS_DOC,
        responses={
            200: OpenApiResponse(description="Usuário reativado com sucesso"),
            400: OpenApiResponse(description="Usuário já está ativo"),
            404: OpenApiResponse(description="Usuário não encontrado"),
        },
    )
    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):

        user = self.get_object()

        if user.is_active:
            return Response(
                {"detail": "Usuário já está ativo."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ct = ContentType.objects.get_for_model(User)

        HistoricoGeral.objects.create(
            content_type=ct,
            object_id=str(user.pk),
            campo="is_active",
            valor_antigo="False",
            valor_novo="True",
            alterado_por=request.user,
            justificativa="Usuário reativado",
        )

        user.is_active = True
        user.save(update_fields=["is_active"])

        return Response(
            {"detail": "Usuário reativado com sucesso."},
            status=status.HTTP_200_OK,
        )
