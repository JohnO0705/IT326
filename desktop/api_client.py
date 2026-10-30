"""HTTP client. The desktop never connects directly to the database."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import ProxyHandler, Request, build_opener


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        if urlparse(self.base_url).scheme not in {"http", "https"}:
            raise ValueError("The API address must begin with http:// or https://.")
        local = urlparse(self.base_url).hostname in {"127.0.0.1", "localhost", "::1"}
        self.opener = build_opener(ProxyHandler({})) if local else build_opener()
        self.token = None

    def request(self, method: str, path: str, data: dict | None = None, params: dict | None = None):
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        headers = {"Accept": "application/json", "User-Agent": "TaskBuddy-Desktop/0.1"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        payload = None
        if data is not None:
            headers["Content-Type"] = "application/json"
            payload = json.dumps(data).encode("utf-8")
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=12) as response:
                body = response.read()
                return json.loads(body.decode("utf-8")) if body else None
        except HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail", "The request could not finish.")
                if isinstance(detail, list):
                    lines = []
                    for item in detail[:3]:
                        location = item.get("loc", [])
                        field = str(location[-1]).replace("_", " ").capitalize() if location else "Details"
                        message = item.get("msg", "Check this value.").removeprefix("Value error, ")
                        lines.append(f"{field}: {message}")
                    detail = "\n".join(lines)
            except (ValueError, UnicodeDecodeError, AttributeError):
                detail = "The server could not finish the request. Please try again."
            raise ApiError(str(detail), error.code) from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            raise ApiError(
                "Could not reach the TaskBuddy server. Make sure the backend is running "
                "and the API address is correct."
            ) from None

    def health(self):
        return self.request("GET", "/health")

    def login(self, username: str, password: str):
        result = self.request("POST", "/auth/login", {"username": username, "password": password})
        self.token = result["access_token"]
        return result

    def register(self, username: str, email: str, password: str):
        result = self.request("POST", "/auth/register", {"username": username, "email": email, "password": password})
        self.token = result["access_token"]
        return result

    def logout(self):
        try:
            return self.request("POST", "/auth/logout")
        finally:
            self.token = None

    def tasks(self, **params):
        return self.request("GET", "/tasks", params=params)

    def create_task(self, title: str, description: str):
        return self.request("POST", "/tasks", {"title": title, "description": description})

    def update_task(self, task_id: int, **changes):
        return self.request("PATCH", f"/tasks/{task_id}", changes)

    def delete_task(self, task_id: int):
        return self.request("DELETE", f"/tasks/{task_id}")

    def restore_task(self, task_id: int):
        return self.request("POST", f"/tasks/{task_id}/restore")

    def empty_deleted(self):
        return self.request("DELETE", "/tasks/deleted")
