import asyncio
import shlex
import threading
from unittest.mock import Mock

import pytest
from embedded_test_framework.helpers.he_linux_host import LinuxHelper
from embedded_test_framework.lib.command_result import CommandResult


def engine_with_result(stdout="", status=0, stderr=""):
    engine = Mock()
    engine.exec_command.return_value = CommandResult(stdout, status, stderr)
    return engine


def test_kernel_release_and_empty_output():
    engine = engine_with_result("6.6.12-custom\n")
    assert LinuxHelper(engine).get_kernel_version(timeout=7) == "6.6.12-custom"
    engine.exec_command.assert_called_once_with("uname -r", timeout=7)
    with pytest.raises(RuntimeError, match="empty kernel"):
        LinuxHelper(engine_with_result()).get_kernel_version()


def test_execute_retains_failure_details_and_can_disable_check():
    helper = LinuxHelper(engine_with_result("out", 13, "permission denied"))
    with pytest.raises(RuntimeError, match="permission denied"):
        helper.execute("false")
    result = helper.execute("false", check=False)
    assert isinstance(result, CommandResult)
    assert (result.stdout, result.exit_status, result.stderr) == ("out", 13, "permission denied")
    assert not result


@pytest.mark.parametrize(
    "program,expected", [("uname", "uname"), ("./my app", "././my app"), ("/tmp/a;b", "/tmp/a;b"), ("-app", "./-app"), ("if", "if")]
)
def test_run_program_quotes_arguments(program, expected):
    engine = engine_with_result("done")
    arguments = ("--name", "a b", "$(touch /tmp/unsafe)", "x;y", "a'b", "", "line\nbreak")
    result = LinuxHelper(engine).run_program(program, *arguments, timeout=9)
    command = engine.exec_command.call_args.args[0]
    assert shlex.split(command) == ["exec", expected, *arguments]
    assert engine.exec_command.call_args.kwargs == {"timeout": 9}
    assert result.stdout == "done"


def test_run_program_failure_and_timeout_propagate():
    engine = engine_with_result("", 127, "not found")
    helper = LinuxHelper(engine)
    with pytest.raises(RuntimeError, match="not found"):
        helper.run_program("missing")
    assert helper.run_program("missing", check=False).exit_status == 127
    engine.exec_command.side_effect = TimeoutError("SSH timeout")
    with pytest.raises(TimeoutError):
        helper.run_program("app")


def test_permission_and_termination_commands():
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    helper.make_executable("-my app;echo bad", timeout=4)
    command = engine.exec_command.call_args.args[0]
    assert shlex.split(command) == ["chmod", "u+x", "./-my app;echo bad"]
    helper.kill_process(123, timeout=5)
    engine.exec_command.assert_called_with("kill -s TERM 123", timeout=5)
    engine.exec_command.return_value = CommandResult("", 1, "denied")
    with pytest.raises(RuntimeError):
        helper.make_executable("app")
    with pytest.raises(RuntimeError):
        helper.kill_process(123)


@pytest.mark.parametrize("pid", [0, -1, True, 1.2, "1; reboot"])
def test_invalid_pid_never_executes(pid):
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    with pytest.raises(ValueError):
        helper.kill_process(pid)
    with pytest.raises(ValueError):
        helper.get_process_memory(pid)
    assert engine.mock_calls == []


@pytest.mark.parametrize("value", ["", None, 1, "bad\x00path"])
def test_invalid_program_and_path_never_execute(value):
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    with pytest.raises(ValueError):
        helper.run_program(value)
    with pytest.raises(ValueError):
        helper.make_executable(value)
    assert engine.mock_calls == []


@pytest.mark.parametrize("timeout", [0, -1, True, float("nan"), float("inf"), "3"])
def test_invalid_timeout_never_executes(timeout):
    engine = engine_with_result()
    with pytest.raises(ValueError):
        LinuxHelper(engine).execute("true", timeout=timeout)
    assert engine.mock_calls == []


def test_invalid_arguments_and_unsupported_engine():
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    for arg in (None, 1, "bad\x00argument"):
        with pytest.raises(ValueError):
            helper.run_program("app", arg)
    assert engine.mock_calls == []
    with pytest.raises(TypeError, match="exec_command"):
        LinuxHelper(object()).execute("true")


def test_existing_text_api_is_preserved():
    engine = Mock()
    engine.exec_command.return_value = CommandResult("contents")
    assert LinuxHelper(engine).read_text("/tmp/file") == "contents"
    engine.exec_command.assert_called_once_with("cat /tmp/file", timeout=None)


@pytest.mark.parametrize("direction,flags", [("upload", []), ("download", ["-R"]), ("bidirectional", ["--bidir"])])
def test_async_iperf_direction_and_report(direction, flags):
    engine = engine_with_result('{"end": {"sum_received": {"bits_per_second": 1234}}}')
    report = asyncio.run(LinuxHelper(engine).iperf("192.0.2.1", direction=direction, duration=5, port=5202))
    assert report["end"]["sum_received"]["bits_per_second"] == 1234
    assert shlex.split(engine.exec_command.call_args.args[0]) == [
        "exec",
        "timeout",
        "-k",
        "2",
        "15",
        "iperf3",
        "-c",
        "192.0.2.1",
        "-p",
        "5202",
        "-t",
        "5",
        "-J",
        *flags,
    ]


@pytest.mark.parametrize("output,status", [('{"error":"server busy"}', 0), ("[]", 0), ("broken json", 0), ("", 127), ("", 124)])
def test_async_iperf_failures(output, status):
    with pytest.raises((ValueError, RuntimeError)):
        asyncio.run(LinuxHelper(engine_with_result(output, status)).iperf("server"))


def test_continuous_ping_yields_packet_loss_and_stops_on_error():
    engine = engine_with_result()
    engine.exec_command.side_effect = [CommandResult("reply"), CommandResult("loss", 1), CommandResult("", 2, "invalid host")]

    async def check():
        stream = LinuxHelper(engine).ping("192.0.2.1", interval=0, reply_timeout=2)
        assert (await anext(stream)).exit_status == 0
        assert (await anext(stream)).exit_status == 1
        with pytest.raises(RuntimeError, match="invalid host"):
            await anext(stream)
        await stream.aclose()

    asyncio.run(check())
    assert shlex.split(engine.exec_command.call_args.args[0]) == [
        "exec",
        "timeout",
        "-k",
        "2",
        "4",
        "ping",
        "-n",
        "-c",
        "1",
        "-W",
        "2",
        "192.0.2.1",
    ]


def test_ping_can_be_closed_without_starting_another_probe():
    engine = engine_with_result("reply")

    async def check():
        stream = LinuxHelper(engine).ping("server", interval=0)
        await anext(stream)
        await stream.aclose()
        await asyncio.sleep(0)

    asyncio.run(check())
    assert engine.exec_command.call_count == 1


def test_async_execution_does_not_block_loop_and_cancellation_drains_worker():
    engine = engine_with_result()
    started, release = threading.Event(), threading.Event()

    def blocking(*args, **kwargs):
        started.set()
        if not release.wait(3):
            raise TimeoutError("test worker was not released")
        return CommandResult("{}")

    engine.exec_command.side_effect = blocking

    async def check():
        task = asyncio.create_task(LinuxHelper(engine).iperf("server"))
        try:
            for _ in range(200):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            assert started.is_set()
            task.cancel()
            await asyncio.sleep(0.01)
            assert not task.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())


@pytest.mark.parametrize("options", [{"duration": 0}, {"duration": True}, {"port": 65536}, {"direction": "both"}])
def test_invalid_iperf_options_never_execute(options):
    engine = engine_with_result()
    with pytest.raises(ValueError):
        asyncio.run(LinuxHelper(engine).iperf("server", **options))
    assert engine.mock_calls == []


@pytest.mark.parametrize("host", ["", "-bad", "a b", "a\x00b", None])
def test_invalid_network_host_never_executes(host):
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    with pytest.raises(ValueError):
        asyncio.run(helper.iperf(host))
    with pytest.raises(ValueError):
        asyncio.run(anext(helper.ping(host)))
    assert engine.mock_calls == []


@pytest.mark.parametrize("options", [{"interval": -1}, {"interval": float("nan")}, {"reply_timeout": 0}, {"reply_timeout": True}])
def test_invalid_ping_options_never_execute(options):
    engine = engine_with_result()
    with pytest.raises(ValueError):
        asyncio.run(anext(LinuxHelper(engine).ping("server", **options)))
    assert engine.mock_calls == []


def test_service_uses_bound_connection_inherits_timeout_and_protects_option_boundary():
    engine = engine_with_result()
    helper = LinuxHelper(engine)
    helper.service("--unexpected; echo bad", "restart")
    assert shlex.split(engine.exec_command.call_args.args[0]) == ["systemctl", "restart", "--", "--unexpected; echo bad"]
    assert engine.exec_command.call_args.kwargs == {"timeout": None}
    engine.exec_command.return_value = CommandResult("inactive", 3)
    assert helper.service("app", "status").exit_code == 3
    with pytest.raises(RuntimeError):
        helper.service("app", "start")
