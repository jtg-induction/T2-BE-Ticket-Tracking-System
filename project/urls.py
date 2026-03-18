from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ProjectViewSet

router = DefaultRouter()
router.register(r"project", ProjectViewSet, basename="project")

urlpatterns = [
    path("", include(router.urls)),
]
