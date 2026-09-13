import sys


def test_host_command(dut):
    result = dut.host.run([sys.executable, "-c", "print('ready')"])
    assert result.ok
    assert result.stdout.strip() == "ready"
