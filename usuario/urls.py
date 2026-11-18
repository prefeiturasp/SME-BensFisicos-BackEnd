from rest_framework.routers import DefaultRouter

from usuario.views import UsuarioViewSet

router = DefaultRouter()
router.register(r"", UsuarioViewSet, basename="usuario")

urlpatterns = router.urls
