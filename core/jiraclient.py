import requests


class JiraClient:
    """
    A low-level HTTP client for interacting with the Jira Cloud REST API.

    Handles authentication, header management, and provides wrapper methods
    for common HTTP verbs.
    """

    DEFAULT_TIMEOUT_SECONDS = 30

    def __init__(self, site_url, user_email, api_token):
        """
        Initializes the Jira client with site credentials.

        Args:
            site_url (str): The base URL of the Jira instance.
            user_email (str): The email address of the Atlassian user.
            api_token (str): The Jira API token of user.
        """
        self.base_url = site_url.rstrip("/")
        self.auth = (user_email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def post(self, endpoint, data):
        """
        Performs an authenticated POST request to a Jira API endpoint.

        Args:
            endpoint (str): The API path.
            data (dict): The JSON payload to be sent.

        Returns:
            requests.Response: The response from the Jira API.
        """
        url = f"{self.base_url}{endpoint}"
        return requests.post(
            url,
            json=data,
            auth=self.auth,
            headers=self.headers,
            timeout=self.DEFAULT_TIMEOUT_SECONDS,
        )

    def put(self, endpoint, data):
        """
        Performs an authenticated PUT request to a Jira API endpoint.

        Args:
            endpoint (str): The API path.
            data (dict): The JSON payload with updated fields.

        Returns:
            requests.Response: The raw response from the Jira API.
        """
        url = f"{self.base_url}{endpoint}"
        return requests.put(
            url,
            json=data,
            auth=self.auth,
            headers=self.headers,
            timeout=self.DEFAULT_TIMEOUT_SECONDS,
        )
