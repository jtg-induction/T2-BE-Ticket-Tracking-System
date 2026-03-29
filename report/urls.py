from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import DownloadReportViewSet, TicketReportView

router = DefaultRouter()
router.register("download", DownloadReportViewSet, basename="download-report")

urlpatterns = [
    path("", TicketReportView.as_view(), name="generate-report"),
    path("", include(router.urls)),
]
