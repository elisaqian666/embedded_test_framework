from unittest.mock import Mock

from embedded_framework.communication.httpengine import HttpEngine


def test_get_uses_configured_url_and_timeout() -> None:
    engine = HttpEngine("http://device:8080/api", timeout=3)
    engine.session.request = request = Mock(return_value="response")

    assert engine.get("health") == "response"
    request.assert_called_once_with("GET", "http://device:8080/api/health", timeout=3)
