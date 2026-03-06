from usuario.views import UsuarioViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"user", UsuarioViewSet, basename="usuario")

urlpatterns = router.urls
