from django.urls import path

from .views import DownloadReportPDFView, TicketReportView

urlpatterns = [
    path(
        "report/",
        TicketReportView.as_view(),
        name="generate-report",
    ),
    path(
        "report/download/",
        DownloadReportPDFView.as_view(),
        name="download-report",
    ),
]
