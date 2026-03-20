from django.urls import path

from report.views import DownloadReportPDFView, TicketReportView

urlpatterns = [
    path("", TicketReportView.as_view(), name="generate-report"),
    path("download/", DownloadReportPDFView.as_view(), name="download-report"),
]
