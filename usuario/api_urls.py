from django.urls import path
from usuario.api_views import (
    CustomTokenObtainPairView,
    CustomTokenRefreshView,
    CustomTokenVerifyView,
    PasswordResetRequestAPIView,
    PasswordResetConfirmAPIView,
    PasswordChangeAPIView,
    UserProfileAPIView,
)

urlpatterns = [
    path("login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
    path("token/verify/", CustomTokenVerifyView.as_view(), name="token_verify"),
    path("me/", UserProfileAPIView.as_view(), name="user_profile"),
    path(
        "password-reset/",
        PasswordResetRequestAPIView.as_view(),
        name="password_reset_request",
    ),
    path(
        "password-reset-confirm/",
        PasswordResetConfirmAPIView.as_view(),
        name="password_reset_confirm",
    ),
    path("password-change/", PasswordChangeAPIView.as_view(), name="password_change"),
]
