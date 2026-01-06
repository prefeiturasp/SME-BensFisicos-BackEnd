from rest_framework import generics, status, views
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenVerifyView,
)
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from usuario.models import Usuario
from usuario.serializers import (
    CustomTokenObtainPairSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    PasswordChangeSerializer,
    UserProfileSerializer,
)
from django.contrib.auth.tokens import PasswordResetTokenGenerator


def set_refresh_token_cookie(response, refresh_token):
    secure = getattr(settings, "SESSION_COOKIE_SECURE", not settings.DEBUG)
    samesite = "Lax"

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=7 * 24 * 60 * 60,
    )


@extend_schema(
    summary="Login",
    description="Autentica usuário e retorna access token. O refresh token é definido em um cookie HttpOnly seguro e removido do corpo da resposta.",
    responses={
        200: OpenApiResponse(
            description="Login realizado com sucesso",
            examples=[
                OpenApiExample(
                    "Sucesso",
                    value={
                        "access": "eyJhbGc...",
                        "user": {
                            "id": 1,
                            "username": "usuario",
                            "nome": "Nome Completo",
                            "rf": "1234567",
                            "is_gestor_patrimonio": True,
                            "is_operador_inventario": False,
                            "must_change_password": False,
                        },
                    },
                )
            ],
        ),
        401: OpenApiResponse(description="Credenciais inválidas"),
    },
    tags=["Autenticação"],
)
class CustomTokenObtainPairView(TokenObtainPairView):

    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if "refresh" in response.data:
            refresh_token = response.data["refresh"]
            set_refresh_token_cookie(response, refresh_token)
            del response.data["refresh"]

        return response


@extend_schema(
    summary="Renovar token de acesso",
    description="Renova o access token usando o refresh token (buscando automaticamente no cookie HttpOnly se não estiver no body).",
    responses={
        200: OpenApiResponse(
            description="Token renovado com sucesso",
            examples=[
                OpenApiExample(
                    "Sucesso",
                    value={
                        "access": "eyJhbGc...",
                    },
                )
            ],
        ),
        401: OpenApiResponse(description="Refresh token inválido ou expirado"),
    },
    tags=["Autenticação"],
)
class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        data = request.data.copy()

        if "refresh" not in data and "refresh_token" in request.COOKIES:
            data["refresh"] = request.COOKIES["refresh_token"]

        serializer = self.get_serializer(data=data)

        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            response = Response(
                {"detail": "Token inválido ou expirado."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
            response.delete_cookie("refresh_token")
            return response

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        if "refresh" in response.data:
            refresh_token = response.data["refresh"]
            set_refresh_token_cookie(response, refresh_token)
            del response.data["refresh"]

        return response


@extend_schema(
    summary="Logout",
    description="Realiza logout removendo o cookie seguro de refresh token e invalidando-o (blacklist).",
    responses={
        200: OpenApiResponse(description="Logout realizado com sucesso"),
    },
    tags=["Autenticação"],
)
class LogoutAPIView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception:
                pass

        response = Response({"detail": "Logout realizado com sucesso."})
        response.delete_cookie("refresh_token")
        return response


@extend_schema(
    summary="Verificar token",
    description="Verifica se um token JWT é válido e não expirou.",
    responses={
        200: OpenApiResponse(
            description="Token válido",
            examples=[OpenApiExample("Sucesso", value={})],
        ),
        401: OpenApiResponse(
            description="Token inválido ou expirado",
            examples=[
                OpenApiExample(
                    "Token inválido",
                    value={
                        "detail": "Token is invalid or expired",
                        "code": "token_not_valid",
                    },
                )
            ],
        ),
    },
    tags=["Autenticação"],
)
class CustomTokenVerifyView(TokenVerifyView):

    pass


@extend_schema(
    summary="Solicitar recuperação de senha",
    description="Envia email com link para redefinir senha. Por segurança, sempre retorna sucesso mesmo se o email não existir.",
    responses={
        200: OpenApiResponse(
            description="Email enviado (se o email existir no sistema)",
            examples=[
                OpenApiExample(
                    "Sucesso",
                    value={
                        "detail": "Se o email informado estiver cadastrado, você receberá instruções para recuperação de senha."
                    },
                )
            ],
        ),
    },
    tags=["Autenticação"],
    auth=None,
)
class PasswordResetRequestAPIView(generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            from django.utils.http import urlsafe_base64_encode
            from django.utils.encoding import force_bytes

            user = Usuario.objects.get(email=email, is_active=True)
            token_generator = PasswordResetTokenGenerator()
            reset_token = token_generator.make_token(user)
            uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
            reset_url = (
                f"{settings.FRONTEND_URL}/recuperar-senha/{uidb64}/{reset_token}/"
            )

            context = {
                "user": user,
                "reset_url": reset_url,
            }

            subject = "Recuperação de Senha - SME Bens Físicos"
            html_message = render_to_string(
                "admin/password_recovery_email_api.html", context
            )

            send_mail(
                subject,
                "",
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                html_message=html_message,
                fail_silently=False,
            )
        except Usuario.DoesNotExist:
            pass

        return Response(
            {
                "detail": "Se o email informado estiver cadastrado, você receberá instruções para recuperação de senha."
            },
            status=status.HTTP_200_OK,
        )


@extend_schema(
    summary="Confirmar recuperação de senha",
    description="Redefine a senha usando o token recebido por email (uidb64 e token).",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "uidb64": {"type": "string", "example": "MTg5"},
                "token": {
                    "type": "string",
                    "example": "d1evfw-ef95e2affcf280870aaee4f3ab6d89fc",
                },
                "new_password": {"type": "string", "example": "NovaSenha123"},
                "new_password_confirm": {"type": "string", "example": "NovaSenha123"},
            },
            "required": ["uidb64", "token", "new_password", "new_password_confirm"],
        }
    },
    responses={
        200: OpenApiResponse(
            description="Senha redefinida com sucesso",
            examples=[
                OpenApiExample(
                    "Sucesso",
                    value={"detail": "Senha redefinida com sucesso."},
                )
            ],
        ),
        400: OpenApiResponse(
            description="Token inválido ou senhas não conferem",
            examples=[
                OpenApiExample(
                    "Token inválido",
                    value={"token": ["Token inválido ou expirado."]},
                )
            ],
        ),
    },
    tags=["Autenticação"],
    auth=None,
)
class PasswordResetConfirmAPIView(generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Senha redefinida com sucesso."}, status=status.HTTP_200_OK
        )


@extend_schema(
    summary="Trocar senha",
    description="Permite que o usuário autenticado troque sua senha atual.",
    responses={
        200: OpenApiResponse(
            description="Senha alterada com sucesso",
            examples=[
                OpenApiExample(
                    "Sucesso",
                    value={"detail": "Senha alterada com sucesso."},
                )
            ],
        ),
        400: OpenApiResponse(
            description="Senha atual incorreta ou senhas não conferem",
            examples=[
                OpenApiExample(
                    "Senha incorreta",
                    value={"old_password": ["Senha atual incorreta."]},
                )
            ],
        ),
        401: OpenApiResponse(description="Não autenticado"),
    },
    tags=["Autenticação"],
)
class PasswordChangeAPIView(generics.GenericAPIView):

    serializer_class = PasswordChangeSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Senha alterada com sucesso."}, status=status.HTTP_200_OK
        )


@extend_schema(
    summary="Obter perfil do usuário",
    description="Retorna os dados do usuário autenticado.",
    responses={
        200: UserProfileSerializer,
        401: OpenApiResponse(description="Não autenticado"),
    },
    tags=["Autenticação"],
)
class UserProfileAPIView(generics.RetrieveAPIView):

    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
