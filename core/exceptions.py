from rest_framework.exceptions import APIException


class JiraBaseException(APIException):
    status_code = 500
    default_detail = "A Jira service error occurred."

    def __init__(self, detail=None, code=None):
        super().__init__(detail, code)


class JiraConnectionError(JiraBaseException):
    status_code = 502
    default_detail = "Jira service is currently unreachable."


class JiraValidationError(JiraBaseException):
    status_code = 400
    default_detail = "Invalid data provided to Jira."


class JiraAuthenticationError(JiraBaseException):
    status_code = 500
    default_detail = "Wrong creds provided to Jira."
