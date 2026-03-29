class ReportMessages:
    """
    Error and validation messages for the reporting system.
    """

    PROJECT_NOT_FOUND = "Project not found."
    PERMISSION_DENIED = "You don't have permission to see detailed ticket data."
    FILE_NOT_FOUND = "File {filename} not found at {path}"
    GENERATION_STARTED = "Report generation started."


class ReportConstants:
    """
    Hardcoded labels, headers, and UI strings for reports and PDF generation.
    """

    REPORT_TITLE = "Ticket Intelligence Report"
    SECTION_DISTRIBUTION = "1 & 2. Status and Priority Distribution"
    SECTION_EFFICIENCY = "3. Efficiency & Completion Metrics"
    SECTION_TIMELINE = "4. Historical Timeline Trends"
    SECTION_INVENTORY = "5. Detailed Ticket Inventory"

    COL_STATUS = "Status"
    COL_PRIORITY = "Priority"
    COL_COUNT = "Count"
    COL_METRIC = "Metric"
    COL_PERIOD = "Period"
    COL_TICKET_NAME = "Ticket Name"
    COL_PROJECT = "Project"
    COL_JIRA_ID = "Jira ID"
    COL_ASSIGNEE = "Assignee Email"
    COL_REPORTER = "Reporter Email"
    COL_UPDATED = "Updated At"
    COL_SPILLED = "Spilled"

    LABEL_COMPLETED = "Project Completed"
    LABEL_INCOMPLETE = "Project Incomplete"
    LABEL_MET_DEADLINE = "Met Deadline"
    LABEL_MISSED_DEADLINE = "Missed Deadline"
    LABEL_NO_DEADLINE = "Completed (No Deadline)"
    ALL_PROJECTS = "All Projects"

    REPORTS_DIR = "reports"
    PDF_CONTENT_TYPE = "application/pdf"
    FETCH_URL_PATH = "fetch/(?P<filename>[^/]+)"
