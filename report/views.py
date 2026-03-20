from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from report.pdf_generator import TicketReportPDF
from report.serializers import ReportSerializer


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


class DownloadReportPDFView(APIView):
    """
    This is the endpoint that actually triggers the PDF file generation.

    Unlike the dashboard view, we explicitly set 'include_details=True'
    because someone downloading a PDF usually wants the full,
    comprehensive list of tickets at the end of the report.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = ReportSerializer(
            data={}, context={"request": request}, include_details=True
        )
        serializer.is_valid(raise_exception=True)

        pdf_gen = TicketReportPDF(serializer.data)
        pdf_buffer = pdf_gen.generate()

        response = HttpResponse(pdf_buffer, content_type="application/pdf")
        response["Content-Disposition"] = 'attachment; filename="Ticket_Report.pdf"'
        return response
