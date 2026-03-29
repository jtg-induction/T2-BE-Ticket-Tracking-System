import os

from celery.result import AsyncResult
from django.conf import settings
from django.http import FileResponse, Http404
from django.urls import reverse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from report.constants import ReportConstants, ReportMessages
from report.permissions import IsProjectMember
from report.serializers import ReportSerializer
from report.tasks import generate_ticket_report_task


class TicketReportView(APIView):
    """
    Returns JSON data for visual reports. Restricted to project members.
    """

    permission_classes = [IsAuthenticated, IsProjectMember]

    def get(self, request, *args, **kwargs):
        serializer = ReportSerializer(data={}, context={"request": request})
        serializer.is_valid(raise_exception=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DownloadReportViewSet(viewsets.ViewSet):
    """
    Handles PDF generation tasks. Restricted to project members.
    """

    permission_classes = [IsAuthenticated, IsProjectMember]

    @action(detail=False, methods=["get"])
    def generate(self, request):
        """Starts the background report generation."""
        task = generate_ticket_report_task.delay(
            request.query_params.dict(), request.user.user_id
        )
        return Response(
            {"task_id": task.id, "message": ReportMessages.GENERATION_STARTED},
            status=status.HTTP_202_ACCEPTED,
        )

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        """Checks the status of a specific generation task."""
        task_result = AsyncResult(pk)
        response_data = {"task_id": pk, "status": task_result.status}

        if task_result.status == "SUCCESS":
            filename = os.path.basename(task_result.result)
            download_url = request.build_absolute_uri(
                reverse("download-report-fetch-pdf", kwargs={"filename": filename})
            )
            response_data["download_url"] = download_url

        return Response(response_data)

    @action(detail=False, methods=["get"], url_path=ReportConstants.FETCH_URL_PATH)
    def fetch_pdf(self, request, filename):
        """Serves the actual PDF file from storage."""
        file_path = os.path.join(
            settings.MEDIA_ROOT, ReportConstants.REPORTS_DIR, filename
        )

        if not os.path.exists(file_path):
            raise Http404(
                ReportMessages.FILE_NOT_FOUND.format(filename=filename, path=file_path)
            )

        file_handle = open(file_path, "rb")
        response = FileResponse(
            file_handle, content_type=ReportConstants.PDF_CONTENT_TYPE
        )
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
