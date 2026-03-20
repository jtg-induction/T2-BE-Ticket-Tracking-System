import requests


class JiraClient:
    def __init__(self, site_url, user_email, api_token):
        self.base_url = site_url.rstrip("/")
        self.auth = (user_email, api_token)
        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        return requests.get(
            url,
            params=params,
            auth=self.auth,
            headers=self.headers,
        )

    def post(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        return requests.post(url, json=data, auth=self.auth, headers=self.headers)

    def put(self, endpoint, data):
        url = f"{self.base_url}{endpoint}"
        return requests.put(url, json=data, auth=self.auth, headers=self.headers)

    def delete(self, endpoint, params=None):
        url = f"{self.base_url}{endpoint}"
        return requests.delete(
            url,
            params=params,
            auth=self.auth,
            headers=self.headers,
        )
