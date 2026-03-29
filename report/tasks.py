import uuid

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from report.pdf_generator import TicketReportPDF
from report.serializers import ReportSerializer

User = get_user_model()


@shared_task(bind=True)
def generate_ticket_report_task(self, query_params, user_id):
    user = User.objects.get(pk=user_id)

    class MockRequest:
        def __init__(self, user, params):
            self.user = user
            self.query_params = params

    mock_request = MockRequest(user, query_params)

    serializer = ReportSerializer(
        data={}, context={"request": mock_request}, include_details=True
    )
    serializer.is_valid(raise_exception=True)

    pdf_gen = TicketReportPDF(serializer.data)
    pdf_buffer = pdf_gen.generate()

    filename = f"reports/Ticket_Report_{uuid.uuid4()}.pdf"
    saved_path = default_storage.save(filename, ContentFile(pdf_buffer.getvalue()))

    return default_storage.url(saved_path)
