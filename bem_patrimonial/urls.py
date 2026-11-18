from rest_framework.routers import DefaultRouter

from bem_patrimonial.views import BemPatrimonialViewSet

router = DefaultRouter()
router.register(r"", BemPatrimonialViewSet, basename="bens")

urlpatterns = router.urls
