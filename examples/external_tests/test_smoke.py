from embedded_test_framework.services import SystemService


def test_version(dut):
    assert "VERSION_ID=1.0" in SystemService(dut).version()
