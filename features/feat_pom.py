"""Example Page Object for an embedded-device WebUI login page."""

from embedded_test_framework.helpers.he_pywright import PlaywrightHelper


class LoginPage:
    """Example login page; replace selectors with the target WebUI's selectors."""

    username = 'input[name="username"]'
    password = 'input[name="password"]'
    submit = 'button[type="submit"]'
    welcome = "#welcome"

    def __init__(self, web: PlaywrightHelper) -> None:
        self.web = web

    def login(self, username: str, password: str) -> str:
        self.web.goto("/login")
        self.web.fill(self.username, username)
        self.web.fill(self.password, password)
        self.web.click(self.submit)
        return self.web.text(self.welcome)
