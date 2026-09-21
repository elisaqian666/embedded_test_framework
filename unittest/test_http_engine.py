import pytest
from unittest.mock import Mock

from embedded_framework.communication.httpengine import HttpEngine


def test_get_uses_configured_url_and_timeout() -> None:
    engine = HttpEngine("http://device:8080/api", timeout=3)
    engine.session.request = request = Mock(return_value="response")

    assert engine.get("health") == "response"
    request.assert_called_once_with("GET", "http://device:8080/api/health", timeout=3)


def test_request_strips_slashes_and_preserves_explicit_timeout() -> None:
    engine = HttpEngine("https://device/api/")
    engine.session.request = request = Mock(return_value="response")

    assert engine.post("/items", timeout=5, json={"name": "item"}) == "response"
    request.assert_called_once_with("POST", "https://device/api/items", timeout=5, json={"name": "item"})


def test_constructor_rejects_invalid_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        HttpEngine("ftp://device/api")


def test_request_rejects_absolute_path() -> None:
    with pytest.raises(ValueError, match="path must be relative"):
        HttpEngine("https://device/api").get("https://other-device/status")
