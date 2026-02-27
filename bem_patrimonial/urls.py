from bem_patrimonial.views import BemPatrimonialViewSet
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r"", BemPatrimonialViewSet, basename="bens")

urlpatterns = router.urls
