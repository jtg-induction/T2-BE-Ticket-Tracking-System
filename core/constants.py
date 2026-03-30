from reportlab.lib import colors

# Project Constants
DEFAULT_PROJECT_TYPE = "software"
KANBAN_TEMPLATE = "com.pyxis.greenhopper.jira:gh-simplified-agility-kanban"
ASSIGNEE_TYPE_LEAD = "PROJECT_LEAD"

# Pagination constants
PAGE_SIZE = 10
MAX_PAGE_SIZE = 50

# Theme constants
PRIMARY_COLOR = colors.HexColor("#0069FE")
SECONDARY_COLOR = colors.HexColor("#E6F0FF")
ACCENT_RED = colors.HexColor("#E74C3C")

# API Configuration
JIRA_API_VERSION = "/rest/api/3"
DEFAULT_MAX_RESULTS = 50

# Jira Project Roles
ROLE_ADMINISTRATOR = "Administrator"
ROLE_MEMBER = "Member"

# Jira Issue Types & Statuses
ISSUE_TYPE_TASK = "Task"
STATUS_TO_DO = "to do"
STATUS_CLOSED = "closed"
STATUS_DONE = "done"

# ADF Document Structure
ADF_VERSION = 1
ADF_TYPE_DOC = "doc"
ADF_TYPE_PARAGRAPH = "paragraph"
ADF_TYPE_TEXT = "text"

# HTTP Status Codes
HTTP_SUCCESS_CODES = [200, 201, 204]
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_SERVER_ERROR = 500

# Project Actions
ACTION_ARCHIVE = "archive"
ACTION_RESTORE = "restore"
