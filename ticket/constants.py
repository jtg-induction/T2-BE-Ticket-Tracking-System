class TicketMessages:
    """
    User-facing error and validation messages for Ticket operations.
    """

    # Validation Errors
    STATUS_TRANSITION_DENIED = "You can not close the ticket."
    MEMBER_REQUIRED_REPORTER = "User is not a member of this project."
    MEMBER_REQUIRED_ASSIGNEE = "User is not a member of this project."
    REPORTER_IMMUTABLE = "Reporter cannot be changed."
    PROJECT_ARCHIVED = "Cannot edit an archived project."
    TARGET_PROJECT_ARCHIVED = "Target project is archived."
    SITE_MISMATCH = "Cannot move ticket to a different Jira site."

    # Import Errors
    ALREADY_IMPORTED = "This ticket has already been imported."
    TICKET_NOT_FOUND = "Ticket not found or no access."
    REPORTER_NOT_FOUND = "The reporter of this ticket is not part of our environment"


class TicketConstants:
    """
    Static roles and system-level constants for Tickets.
    """

    ROLE_REPORTER = "reporter"
    ROLE_ASSIGNEE = "assignee"
    ROLE_ADMIN = "admin"
    ROLE_MEMBER = "member"
    ROLE_GUEST = "guest"
    ROLE_NONE = "none"
