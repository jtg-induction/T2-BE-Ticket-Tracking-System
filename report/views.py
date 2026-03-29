import os

from celery.result import AsyncResult
from django.conf import settings
from django.http import FileResponse, Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from report.serializers import ReportSerializer

from .tasks import generate_ticket_report_task


class TicketReportView(APIView):
    """
    This view is for the visual report. It returns the raw data (JSON)
    that the frontend needs to render charts and stats.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        serializer = ReportSerializer(data={}, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DownloadReportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def generate(self, request):
        """Kicks off the async task."""
        task = generate_ticket_report_task.delay(
            request.query_params.dict(), request.user.user_id
        )
        return Response(
            {"task_id": task.id, "message": "Report generation started."},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        task_result = AsyncResult(pk)
        response_data = {"task_id": pk, "status": task_result.status}

        if task_result.status == "SUCCESS":
            filename = os.path.basename(task_result.result)
            download_url = request.build_absolute_uri(
                f"/api/report/download/fetch/{filename}/"
            )
            response_data["download_url"] = download_url

        return Response(response_data)

    @action(detail=False, methods=["get"], url_path=r"fetch/(?P<filename>[^/]+)")
    def fetch_pdf(self, request, filename):
        file_path = os.path.join(settings.MEDIA_ROOT, "reports", filename)

        if not os.path.exists(file_path):
            raise Http404(f"File {filename} not found at {file_path}")

        file_handle = open(file_path, "rb")

        response = FileResponse(file_handle, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
