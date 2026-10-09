import pytest
from embedded_test_framework.helpers.he_pywright import PlaywrightHelper


def test_playwright_helper_rejects_invalid_webui_url() -> None:
    with pytest.raises(ValueError):
        PlaywrightHelper("device.local")
