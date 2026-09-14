import pytest

from embedded_test_framework import wait, OperationTimeout, ObservationFailed, ConfigurationError


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(wait.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(wait.time, "sleep", lambda duration: now.__setitem__(0, now[0] + duration))
    return now


def test_polling_variants(clock):
    values = iter([False, False, True])
    assert wait.until_true(lambda: next(values), timeout=1, interval=.1)
    assert wait.until_false(lambda: False) is False
    assert wait.until_equal(lambda: "ready", "ready") == "ready"
    assert clock[0] == .2


def test_only_requested_exceptions_are_retried(clock):
    error = OSError("offline")
    def observe():
        raise error
    with pytest.raises(OperationTimeout) as caught:
        wait.until_no_exception(observe, exceptions=(OSError,), timeout=.25, interval=.1)
    assert caught.value.__cause__ is error
    assert clock[0] == .25
    with pytest.raises(OSError):
        wait.until_true(observe)


def test_no_exception_can_return_false(clock):
    assert wait.until_no_exception(lambda: False, exceptions=(OSError,)) is False


def test_late_success_does_not_escape_deadline(clock):
    def slow():
        clock[0] += 2
        return True
    with pytest.raises(OperationTimeout):
        wait.until_true(slow, timeout=1)


def test_watch_samples_endpoint_and_fails_on_change(clock):
    calls = []
    assert wait.stays_true(lambda: calls.append(clock[0]) or True, duration=.2, interval=.1)
    assert calls == [0, .1, .2]
    values = iter(["up", "down"])
    with pytest.raises(ObservationFailed):
        wait.stays_equal(lambda: next(values), "up", duration=1, interval=.1)


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan")])
def test_invalid_budget_rejected(timeout):
    with pytest.raises(ConfigurationError):
        wait.until_true(lambda: True, timeout=timeout)
