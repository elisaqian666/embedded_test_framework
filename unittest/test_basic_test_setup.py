import logging

import pytest
from pathlib import Path
from types import SimpleNamespace

import embedded_test_framework.basic_test_setup as basic_test_setup
from embedded_test_framework.basic_test_setup import BasicTestClass
import embedded_test_framework.lib.logging_extras as logging_extras


def test_setup_creates_one_timestamped_log_folder(tmp_path, monkeypatch):
    original = logging_extras._TEST_LOG_FOLDER
    monkeypatch.chdir(tmp_path)
    logging_extras._TEST_LOG_FOLDER = None
    try:
        BasicTestClass._initialize_log_folder()
        folder = logging_extras._TEST_LOG_FOLDER
        assert folder is not None and folder.parent == Path(__file__).resolve().parents[2] / "test_logs"
        assert (folder / "test.log").is_file()
        assert (folder / "test-results.txt").is_file()
    finally:
        for handler in logging.getLogger().handlers[:]:
            if isinstance(handler, logging.FileHandler) and folder and handler.baseFilename.startswith(str(folder)):
                logging.getLogger().removeHandler(handler)
                handler.close()
        logging_extras._TEST_LOG_FOLDER = original


def test_setup_creates_method_folders(tmp_path):
    class SampleTestCase(BasicTestClass):
        pass

    SampleTestCase.base_log_store_folder = str(tmp_path)
    SampleTestCase._initialize_log_folder()
    first, second = SampleTestCase(), SampleTestCase()
    first._test_id = "test_example.py::SampleTestCase::test_first"
    second._test_id = "test_example.py::SampleTestCase::test_second"

    first.setUp()
    second.setUp()

    assert Path(first.test_method_log_store_folder).parent == Path(SampleTestCase.test_class_log_store_folder)
    assert first.test_method_log_store_folder != second.test_method_log_store_folder


def test_failure_summary_has_context_error_and_trace(tmp_path, monkeypatch):
    nodeid = "test_example.py::LinuxTest::test_crashes"
    monkeypatch.setattr(basic_test_setup, "_TEST_CONTEXTS", {"test_example.py::LinuxTest": ("linux_dut", "serial_dut")})
    monkeypatch.setattr(basic_test_setup, "_TEST_ARTIFACTS", {nodeid: tmp_path})
    report = SimpleNamespace(
        when="call",
        duration=1.5,
        longreprtext="Traceback (most recent call last):\nRuntimeError: boom",
        longrepr=SimpleNamespace(reprcrash=SimpleNamespace(message="RuntimeError: boom")),
        caplog="ERROR device crashed",
    )

    basic_test_setup._write_summary(nodeid, [report], failed=True)

    summary = (tmp_path / "summary.txt").read_text(encoding="utf-8")
    assert "# 1. Test Context" in summary
    assert "linux_dut, serial_dut" in summary
    assert "# 2. Error Text" in summary and "ERROR device crashed" in summary
    assert "# 3. Call Trace" in summary and "RuntimeError: boom" in summary


def test_success_summary_has_only_test_context(tmp_path, monkeypatch):
    nodeid = "test_example.py::LinuxTest::test_works"
    monkeypatch.setattr(basic_test_setup, "_TEST_CONTEXTS", {"test_example.py::LinuxTest": ("linux_dut",)})
    monkeypatch.setattr(basic_test_setup, "_TEST_ARTIFACTS", {nodeid: tmp_path})
    report = SimpleNamespace(duration=0.2)

    basic_test_setup._write_summary(nodeid, [report], failed=False)

    summary = (tmp_path / "summary.txt").read_text(encoding="utf-8")
    assert "# 1. Test Context" in summary and "linux_dut" in summary
    assert "# 2. Error Text" not in summary and "# 3. Call Trace" not in summary


def test_session_finish_writes_summary_for_a_failed_case(tmp_path, monkeypatch):
    nodeid = "test_example.py::LinuxTest::test_crashes"
    report = SimpleNamespace(
        when="call",
        duration=0.1,
        longreprtext="Traceback (most recent call last):\nAssertionError: boom",
        longrepr=SimpleNamespace(reprcrash=SimpleNamespace(message="AssertionError: boom")),
        caplog="",
    )
    monkeypatch.setattr(basic_test_setup, "setup_test_log_folder", lambda: tmp_path)
    monkeypatch.setattr(basic_test_setup, "_TEST_RESULTS", {nodeid: "FAILED"})
    monkeypatch.setattr(basic_test_setup, "_TEST_FAILURES", {nodeid: [report]})
    monkeypatch.setattr(basic_test_setup, "_TEST_PASSES", {})
    monkeypatch.setattr(basic_test_setup, "_TEST_ARTIFACTS", {nodeid: tmp_path})

    basic_test_setup._TestResultReporter().pytest_sessionfinish(None, 1)

    assert "# 3. Call Trace" in (tmp_path / "summary.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("scope", ["class", "method"])
@pytest.mark.parametrize("failure", [None, "setup", "teardown"])
def test_fixture_always_runs_registered_cleanups(scope, failure, monkeypatch):
    calls = []

    class SampleCase(basic_test_setup.UnittestTestCase):
        @classmethod
        def setUpClass(cls):
            cls.addClassCleanup(calls.append, "cleanup")
            calls.append("setup")
            if failure == "setup":
                raise RuntimeError("setup failed")

        @classmethod
        def tearDownClass(cls):
            calls.append("teardown")
            if failure == "teardown":
                raise RuntimeError("teardown failed")

        def setUp(self):
            self.addCleanup(calls.append, "cleanup")
            calls.append("setup")
            if failure == "setup":
                raise RuntimeError("setup failed")

        def tearDown(self):
            calls.append("teardown")
            if failure == "teardown":
                raise RuntimeError("teardown failed")

    monkeypatch.setattr(basic_test_setup, "setup_test_log_folder", lambda: None)
    monkeypatch.setattr(basic_test_setup, "_register_failed_case_reporter", lambda config: None)
    if scope == "class":
        fixture = SampleCase.setup_teardown_class_fixture._fixture_function
        lifecycle = fixture(SimpleNamespace(config=None))
    else:
        sample = SampleCase()
        sample._test_id = "sample"
        fixture = SampleCase.setup_teardown_fixture._fixture_function
        lifecycle = fixture(sample, None)

    if failure == "setup":
        with pytest.raises(RuntimeError, match="setup failed"):
            next(lifecycle)
    else:
        next(lifecycle)
        if failure == "teardown":
            with pytest.raises(RuntimeError, match="teardown failed"):
                next(lifecycle)
        else:
            with pytest.raises(StopIteration):
                next(lifecycle)

    assert calls == (["setup", "cleanup"] if failure == "setup" else ["setup", "teardown", "cleanup"])
    if scope == "class":
        assert "pytest_request" not in SampleCase.__dict__


@pytest.mark.parametrize("scope", ["class", "method"])
def test_cleanup_errors_are_aggregated_after_all_callbacks_run(scope):
    class SampleCase(basic_test_setup.UnittestTestCase):
        pass

    target = SampleCase if scope == "class" else SampleCase()
    register = target.addClassCleanup if scope == "class" else target.addCleanup
    cleanup = target.doClassCleanups if scope == "class" else target.doCleanups
    calls = []
    failures = [RuntimeError("first failure"), OSError("second failure")]

    def fail(error):
        calls.append(str(error))
        raise error

    register(calls.append, "last cleanup")
    for error in failures:
        register(fail, error)
    with pytest.raises(ExceptionGroup) as caught:
        cleanup()
    assert list(caught.value.exceptions) == list(reversed(failures))
    assert calls == ["second failure", "first failure", "last cleanup"]
    cleanup()


@pytest.mark.parametrize("trace_style", ["no", "short"])
def test_real_pytest_failure_traces_reach_log_and_summary_even_with_shortened_terminal_output(tmp_path, trace_style):
    import subprocess
    import sys
    import textwrap

    run_dir = tmp_path / "artifacts"
    run_dir.mkdir()
    test_file = tmp_path / "test_trace_output.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from pathlib import Path
            from embedded_test_framework.basic_test_setup import BasicTestClass
            from embedded_test_framework.lib import logging_extras

            logging_extras._TEST_LOG_FOLDER = Path(__file__).parent / "artifacts"
            logging_extras.setup_global_logging(log_file=logging_extras._TEST_LOG_FOLDER / "test.log")

            def device_failure():
                raise RuntimeError("device-read-failed")

            def cleanup_failure():
                raise OSError("device-reset-failed")

            class TestCallFailure(BasicTestClass):
                def test_read(self):
                    self.logger.info("first line\\nsecond %(device)s", {"device": "board"})
                    device_failure()

            class TestCleanupFailure(BasicTestClass):
                def test_reset(self):
                    self.addCleanup(cleanup_failure)

            class TestCallAndCleanupFailure(BasicTestClass):
                def test_both(self):
                    self.addCleanup(cleanup_failure)
                    device_failure()

            class TestSetupFailure(BasicTestClass):
                @classmethod
                def setUpClass(cls):
                    super().setUpClass()
                    raise ValueError("class-setup-failed")

                def test_setup(self):
                    pass

            class TestPass(BasicTestClass):
                def test_ok(self):
                    self.logger.info("completed 100%% for %(device)s", {"device": "board"})
            """
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(test_file),
            "--rootdir",
            str(tmp_path),
            "--confcutdir",
            str(tmp_path),
            "-q",
            f"--tb={trace_style}",
            "-p",
            "no:cacheprovider",
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "--- Logging error ---" not in result.stdout + result.stderr
    log = (run_dir / "test.log").read_text(encoding="utf-8")
    for text in (
        "device-read-failed",
        "device-reset-failed",
        "class-setup-failed",
        "device_failure",
        "cleanup_failure",
        "first line",
        "second board",
    ):
        assert text in log
    summaries = [file.read_text(encoding="utf-8") for file in run_dir.rglob("summary.txt")]
    assert len(summaries) == 5
    for failure in ("device-read-failed", "device-reset-failed", "class-setup-failed"):
        summary = next(text for text in summaries if failure in text)
        assert "# 3. Call Trace" in summary
        assert "test_trace_output.py" in summary
    both = next(text for text in summaries if "device-read-failed" in text and "device-reset-failed" in text)
    assert "## call" in both and "## teardown" in both
    passed = next(text for text in summaries if "# 2. Error Text" not in text)
    assert "# 3. Call Trace" not in passed
