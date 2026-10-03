"""Browser automation for embedded-device WebUIs using Playwright."""

from pathlib import Path
from urllib.parse import urljoin, urlparse


class PlaywrightHelper:
    """Own one headless browser session for a configured WebUI endpoint."""

    def __init__(self, base_url: str, *, headless: bool = True, timeout: float = 10) -> None:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or timeout <= 0:
            raise ValueError("base_url must be an HTTP(S) URL and timeout must be positive")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise ImportError("Install playwright and run 'playwright install chromium' to automate WebUI") from error
        self.base_url = base_url.rstrip("/") + "/"
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=headless)
        self.page = self._browser.new_page()
        self.page.set_default_timeout(timeout * 1000)

    def goto(self, path: str = "/") -> None:
        self.page.goto(urljoin(self.base_url, path.lstrip("/")), wait_until="networkidle")

    def click(self, selector: str) -> None:
        self.page.locator(selector).click()

    def fill(self, selector: str, value: str) -> None:
        self.page.locator(selector).fill(value)

    def text(self, selector: str) -> str:
        return self.page.locator(selector).inner_text()

    def screenshot(self, destination: str | Path) -> Path:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def close(self) -> None:
        self._browser.close()
        self._playwright.stop()

    def __enter__(self) -> "PlaywrightHelper":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
