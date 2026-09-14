from ..logging import log_operation
"""Standard-library HTTP transport; no automatic replay of requests."""
import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from .transport_base import HttpResponse, Transport
from ..errors import ConfigurationError, OperationTimeout, TransportError


class HttpTransport(Transport):
    def __init__(self, base_url, *, headers=None, timeout=5.0):
        super().__init__(timeout)
        parts = urllib.parse.urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment or parts.username:
            raise ConfigurationError("base_url must be an HTTP(S) URL without credentials, query or fragment")
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})

    @log_operation
    def connect(self):
        # HTTP has no persistent authenticated session: health is checked by services.
        self.connected = True
        return self

    @log_operation
    def close(self):
        self.connected = False

    @log_operation
    def request(self, method, path, *, payload=None, params=None, headers=None, timeout=None):
        self.require_connected()
        duration = self.operation_timeout(timeout)
        parts = urllib.parse.urlsplit(path)
        if parts.scheme or parts.netloc or parts.fragment:
            raise ConfigurationError("request path must be relative to base_url")
        url = self.base_url + "/" + path.lstrip("/")
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        merged = {**self.headers, **(headers or {})}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            if not any(k.lower() == "content-type" for k in merged):
                merged["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=merged, method=method.upper())
        # Reject redirects so credentials cannot be forwarded to another endpoint.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            try:
                response = opener.open(request, timeout=duration)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                return HttpResponse(response.code, dict(response.headers), response.read())
        except (TimeoutError, socket.timeout) as exc:
            raise OperationTimeout("HTTP request timed out") from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise OperationTimeout("HTTP request timed out") from exc
            raise TransportError("HTTP connection failed") from exc
        except OSError as exc:
            raise TransportError("HTTP I/O failed") from exc
