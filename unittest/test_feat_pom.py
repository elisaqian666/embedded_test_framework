from embedded_test_framework.features.feat_pom import LoginPage


class FakeWeb:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def goto(self, path: str) -> None:
        self.calls.append(("goto", path))

    def fill(self, selector: str, value: str) -> None:
        self.calls.append(("fill", selector, value))

    def click(self, selector: str) -> None:
        self.calls.append(("click", selector))

    def text(self, selector: str) -> str:
        self.calls.append(("text", selector))
        return "Welcome, operator"


def test_login_page_uses_web_helper() -> None:
    web = FakeWeb()

    assert LoginPage(web).login("operator", "secret") == "Welcome, operator"
    assert web.calls == [
        ("goto", "/login"),
        ("fill", 'input[name="username"]', "operator"),
        ("fill", 'input[name="password"]', "secret"),
        ("click", 'button[type="submit"]'),
        ("text", "#welcome"),
    ]
