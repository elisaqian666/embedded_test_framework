"""HTTP transport without device endpoints, model lookup or login policy."""

from typing import Any, Self
from urllib.parse import urlsplit

import requests


class HttpEngine:
    """Own a reusable HTTP session with explicit authentication and TLS settings.

    :param base_url: Absolute HTTP(S) URL, optionally including an API prefix.
    :param timeout: Default request timeout in seconds.
    :param auth: Requests-compatible authentication supplied by the caller.
    :param verify: Verify TLS certificates, or use a supplied CA bundle path.
    :param headers: Application-specific headers supplied by the caller.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 20,
        auth: Any = None,
        verify: bool | str = True,
        headers: dict[str, str] | None = None,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.query or parsed.fragment:
            message = "base_url must be an absolute HTTP(S) URL without a query or fragment"
            raise ValueError(message)
        if timeout <= 0:
            message = "timeout must be positive"
            raise ValueError(message)
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = auth
        self.session.verify = verify
        if headers:
            self.session.headers.update(headers)

    def request(self, method: str, path: str = "", **kwargs: Any) -> requests.Response:
        """Send one request and return its raw response, including non-2xx responses.

        :param method: HTTP method.
        :param path: Relative resource path appended to the configured API prefix.
        :param kwargs: Requests options such as params, json, data, files or stream.
        :returns: Response owned by the caller; close streamed responses after use.

        No automatic retries are performed: replaying a write could repeat a
        device operation. Authentication refresh belongs to the device adapter.
        """
        if urlsplit(path).scheme or path.startswith("//"):
            message = "path must be relative to base_url"
            raise ValueError(message)
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, f"{self.base_url}/{path.lstrip('/')}", **kwargs)

    def get(self, path: str = "", **kwargs: Any) -> requests.Response:
        """Request a resource; use response.json() when JSON is expected."""
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        """Submit a resource using explicit json, data or files arguments."""
        return self.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs: Any) -> requests.Response:
        """Replace a resource."""
        return self.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        """Partially update a resource."""
        return self.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        """Delete a resource."""
        return self.request("DELETE", path, **kwargs)

    def close(self) -> None:
        """Release the session and pooled connections."""
        self.session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def make_http_engine(base_url: str, **kwargs: Any) -> HttpEngine:
    """Create an HTTP engine without contacting a device."""
    return HttpEngine(base_url, **kwargs)
