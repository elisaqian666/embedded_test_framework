# Real-device tests

This directory contains tests that require physical hardware. They are excluded from the default unit test suite and the Jenkins offline tests.

`test_kernel_version.py` uses the framework's SSH interface to log in to `192.168.1.103` as `root`, execute `uname -r`, and verify that the command succeeds and returns a nonempty kernel version. The SSH session is closed when the device context exits, including when an assertion fails.

Run these PowerShell commands from the project root:

```powershell
python -m pip install -e ".[test,ssh]"
# Before first use, verify the host fingerprint through a trusted channel and save the key with OpenSSH.
ssh root@192.168.1.103
# After logging in, enter exit to return to the local machine.
$env:DUT_SSH_PASSWORD = 'letmein'
python -m pytest device_tests/test_kernel_version.py -v -s
Remove-Item Env:DUT_SSH_PASSWORD
```

The password is supplied through an environment variable, not embedded in the test code. SSH validates the device against the local known_hosts file; a missing or mismatched host key causes the connection to fail. The test is skipped if the password is not set.
