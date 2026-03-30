import uuid

from ddf import G
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from project.enums import MemberStatus
from project.models import ProjectMember, ProjectModel
from report.constants import ReportConstants, ReportMessages
from ticket.enums import Priority, Status
from ticket.models import Ticket

User = get_user_model()


class ReportSystemTestCase(APITestCase):
    """
    Suite for validating the report generation lifecycle, including visual data
    aggregation, permission constraints, async task triggering, and file retrieval.
    """

    def setUp(self):
        """
        Initialize a test environment with an owner, a member, and an outsider,
        along with tickets configured to test deadline efficiency metrics.
        """
        self.admin_user = G(User, email="admin@test.com", first_name="Admin")
        self.regular_user = G(User, email="user@test.com", first_name="User")
        self.other_user = G(User, email="other@test.com", first_name="Other")

        self.project = G(ProjectModel, title="Test Project", owner=self.admin_user)

        G(
            ProjectMember,
            project=self.project,
            user=self.regular_user,
            is_admin=False,
            status=MemberStatus.MEMBER,
        )

        G(
            Ticket,
            name="Met Deadline Ticket",
            project=self.project,
            assignee=self.regular_user,
            status=Status.DONE,
            priority=Priority.HIGH,
            deadline="2026-01-01",
            completed_at="2025-12-31",
        )
        G(
            Ticket,
            name="Missed Deadline Ticket",
            project=self.project,
            assignee=self.regular_user,
            status=Status.DONE,
            priority=Priority.LOW,
            deadline="2026-01-01",
            completed_at="2026-01-05",
        )

    def test_get_visual_report_success(self):
        """
        Ensure the visual report endpoint returns the expected statistics and
        project metadata when accessed by an authorized administrator.
        """
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("generate-report")

        response = self.client.get(url, {"project": self.project.id})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("efficiency_stats", response.data)
        self.assertEqual(response.data["metadata"]["project_title"], self.project.title)

    def test_permission_denied_for_unauthorized_project_access(self):
        """
        Verify that users not participating in a project are strictly prohibited
        from accessing detailed project report data.
        """
        self.client.force_authenticate(user=self.other_user)
        url = reverse("generate-report")

        response = self.client.get(url, {"project": self.project.id})

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.data[0], ReportMessages.PERMISSION_DENIED)

    def test_async_report_generation_trigger(self):
        """
        Validate that the PDF generation process successfully enqueues a background
        task and returns a 202 status with a trackable task identifier.
        """
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("download-report-generate")

        response = self.client.get(url, {"project": self.project.id})

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data["message"], ReportMessages.GENERATION_STARTED)

    def test_efficiency_aggregation_logic(self):
        """
        Confirm that the report serializer accurately calculates and groups ticket
        counts based on deadline compliance and priority levels.
        """
        from report.serializers import ReportSerializer

        class MockRequest:
            def __init__(self, user, project_id):
                self.user = user
                self.query_params = {"project": str(project_id)}

        serializer = ReportSerializer(
            context={"request": MockRequest(self.admin_user, self.project.id)}
        )
        eff_stats = serializer.get_efficiency_stats(None)

        met = next(
            i for i in eff_stats if i["label"] == ReportConstants.LABEL_MET_DEADLINE
        )
        missed = next(
            i for i in eff_stats if i["label"] == ReportConstants.LABEL_MISSED_DEADLINE
        )

        self.assertEqual(met[Priority.HIGH.label], 1)
        self.assertEqual(missed[Priority.LOW.label], 1)

    def test_fetch_pdf_from_storage(self):
        """
        Assert that the file retrieval endpoint correctly locates and streams
        generated PDF documents from the configured storage backend.
        """
        self.client.force_authenticate(user=self.admin_user)
        filename = f"test_report_{uuid.uuid4()}.pdf"
        file_path = f"{ReportConstants.REPORTS_DIR}/{filename}"

        default_storage.save(file_path, ContentFile(b"fake pdf content"))

        url = reverse("download-report-fetch-pdf", kwargs={"filename": filename})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], ReportConstants.PDF_CONTENT_TYPE)

        default_storage.delete(file_path)

    def test_metadata_handles_global_scope(self):
        """
        Verify that the report metadata defaults to a global identifier when no
        specific project context is provided in the request parameters.
        """
        self.client.force_authenticate(user=self.admin_user)
        url = reverse("generate-report")

        response = self.client.get(url)

        self.assertEqual(
            response.data["metadata"]["project_title"], ReportConstants.ALL_PROJECTS
        )
