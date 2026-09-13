# Embedded Test Framework

面向独立测试用例仓库的 Python SDK，Python 3.11+。框架负责通信、设备生命周期和可复用服务；产品预期、断言和测试报告由用例仓库负责。

## 分层与目录

```text
独立用例仓库：pytest / unittest / 自定义运行器
                        ↓
services：SystemService / HealthService / FileService / 产品服务
                        ↓
devices：Device（组合多个命名通道，可继承扩展）
                        ↓                    ↘
engine：CommandChannel / RequestChannel / ByteChannel / FileChannel
                        ↓               hosts：LocalHost（主机软件、进程、外设）
                        ↓
SSH / ADB / HTTP / Serial / FTP / Memory / 自定义驱动

src/embedded_test_framework/
  engine/        通信实现、能力接口、结果类型
  devices/           与测试运行器无关的设备对象
  hosts/             主机操作、应用生命周期、进程和外设枚举
  services/          可复用应用流程
  config.py          配置加载、设备工厂、扩展注册
  errors.py          公共异常
  pytest_plugin.py   可选 pytest 集成
configs/             真实设备配置模板
examples/external_tests/  可复制到独立仓库的离线示例
unittest/            框架自身测试
```

核心包只依赖标准库。串口按需安装 pyserial；SSH 使用系统 OpenSSH，ADB 使用 Android platform tools。HTTP 的 connect 仅建立逻辑状态，实际可达性由请求或健康服务验证；SSH 会执行 `true` 验证认证，默认要求 known_hosts 中已有主机密钥，默认使用密钥/agent 认证；传入 password 时使用可选 Paramiko（安装 `[ssh]`）建立密码会话。SSH 命令接口适用于 POSIX shell。

## 安装与独立仓库使用

在用例仓库的虚拟环境中安装本项目（将路径替换为实际目录）：

```powershell
python -m pip install -e "D:/work_project/embedded_test_framework[test,serial]"
```

发布时在框架仓库执行 `python -m pip wheel . --no-deps -w dist`，将 wheel 发布至内部制品库；用例仓库固定版本，如 `embedded-test-framework==0.2.0`。发行包仅包含 `src/embedded_test_framework` 下的 SDK。`build/`、`dist/`、`*.egg-info/` 为自动生成的构建产物，无需提交或手动维护。

普通 Python 调用：

```python
from embedded_test_framework import load_device
from embedded_test_framework.services import SystemService, HealthService

with load_device("devices.json", "dut") as device:
    HealthService(device).wait_ready(timeout=30)
    version = SystemService(device).version()
    print(version)
    response = device.request("GET", "/device/info")
    assert response.ok
    print(response.json())
    raw = device.exchange(b"AT\r\n", delimiter=b"\r\n")
```

根据设备实际能力从 `configs/devices.example.json` 删除不需要的通道。`${DUT_HOST}` 等变量在加载时读取环境，缺失立即报错；构造对象不连接硬件。配置只接受显式注册的类型，不执行配置中的 Python 导入。串口 exchange 不自动补命令结束符，必须由设备驱动编码；超时即使收到部分回复也报错。

pytest 用例仓库：

```python
# conftest.py
pytest_plugins = ["embedded_test_framework.pytest_plugin"]

# test_version.py
from embedded_test_framework.services import SystemService

def test_version(dut):
    assert "VERSION_ID" in SystemService(dut).version()
```

```powershell
pytest --device-config devices.json --device-name dut
```

fixture 每个用例独立连接和释放；相对配置路径以 pytest rootdir 为基准。插件需显式启用，不自动影响其他测试项目。可将 `examples/external_tests` 内容复制到独立仓库直接运行，其中 MemoryTransport 不需要任何硬件。

## 主机层：软件、进程和外设

`Device.host` 默认是运行 Python 的本机，可在 `device.connect()` 前使用。主机层与通信层协作：主机层管理测试环境，通信层负责与板子交换数据。配置中的 `host.name` 是标签，不是远程地址。

```python
from embedded_test_framework import load_device
from embedded_test_framework.services import HostService

# load_device 只构造对象，此时无需串口已连接。
device = load_device("devices.json")
try:
    board = HostService(device.host).wait_for_peripheral(
        kind="serial", vid=0x1234, pid=0x5678,
        serial_number="board-001", timeout=15,
    )
    print(board.identifier)  # 例如 COM3；需与设备 console 配置一致
    with device.host.start_application(
        [r"C:\Tools\BoardMonitor.exe", "--port", board.identifier], visible=True
    ) as app:
        assert app.running
        # 应用启动不等于业务就绪；产品服务应继续检查窗口/API/日志状态。
finally:
    device.close()
```

主机软件若独占串口，需先关闭软件，再连接设备串口通道。`start_application` 传可执行文件和参数列表，默认请求隐藏 Windows 窗口，需展示交互窗口时传 `visible=True`；不提供点击菜单等 GUI 自动化。

```python
processes = device.host.list_processes()
running = device.host.is_process_running("BoardMonitor.exe")  # 完整进程名，忽略大小写
usb_devices = device.host.list_peripherals(kind="usb")        # Windows 当前在场 USB 设备
all_devices = device.host.list_peripherals(kind="pnp")        # Windows 当前在场 PnP 设备
serial_ports = device.host.list_peripherals(kind="serial")    # 跨平台串口
```

安装 `embedded-test-framework[host]` 提供串口枚举与非 Windows 进程枚举依赖。Windows 进程/PnP 枚举使用 PowerShell；PnP/USB 可按完整 InstanceId 或 VID/PID 匹配，USB 序列号不从 InstanceId 猜测。串口序列号由 pyserial 提供。`HostService.find_peripherals(..., healthy_only=True)` 可过滤系统报告的异常设备，但枚举成功不代表板子通信或固件正常。

设备默认拥有内部创建的主机，关闭设备时释放其启动的应用；手动注入 `Device(..., host=shared_host)` 时主机由调用方管理，适合多板共用一台主机：

```python
from embedded_test_framework import Device, LocalHost
from embedded_test_framework.engine import MemoryTransport

with LocalHost() as host:
    with Device("board-a", {"shell": MemoryTransport()}, host=host) as board:
        print(board.host.name)
```

应用句柄只管理直接创建的进程，不终止已有同名程序或整个进程树；启动器派生进程、GUI 应用自行忽略隐藏提示等行为需产品适配。外设等待的 timeout 是轮询预算，单次枚举还受主机命令 timeout 限制，可能超出轮询预算。

可继承 `Host` 并通过 `Registry.register_host` 扩展实验室主机实现。当前通信驱动仍在本机执行；远程主机代理还需要对应的远程通信驱动，修改主机标签不会自动把串口或 ADB 转到远程执行。

## 扩展设备和服务

```python
from embedded_test_framework import Device, Registry, load_device

class SensorBoard(Device):
    def temperature(self):
        # 产品命令和解析放在设备适配器，原始串口保持字节语义。
        raw = self.exchange(b"TEMP?\n", delimiter=b"\n")
        return float(raw.decode("ascii").strip())

class TemperatureService:
    def __init__(self, board):
        self.board = board

    def sample(self, count=3):
        return [self.board.temperature() for _ in range(count)]

registry = Registry.defaults()
registry.register_device("sensor-board", SensorBoard)
# 配置中设备 type 设为 sensor-board。
with load_device("devices.json", registry=registry) as board:
    assert all(0 <= value <= 80 for value in TemperatureService(board).sample())
```

新增 CAN、Modbus、BLE、JTAG 等协议：继承 `Transport` 实现 connect/close，再实现所需的能力方法（例如 exchange），通过 `registry.register_transport("can", MyCanTransport)` 注册。构造函数只存配置，connect 负责打开资源，close 必须可重复调用。不同设备对象不得共享同一 transport。专有寄存器、烧录、复位语义在设备子类中实现，不强行映射成 HTTP request。

在用例仓库覆盖 `device_registry` fixture，返回包含产品扩展的 Registry 即可。BLE GATT 通信需要增加独立适配器。

## 行为约定

- 设备对象不继承 unittest.TestCase；断言留在用例中，统一通过 `embedded_test_framework` 包调用。
- 命令返回 CommandResult，非零退出码由 `.check()` 转为异常；HTTP 返回 HttpResponse，包含非 2xx 状态，由服务或用例判断。
- 连接失败按逆序释放已尝试打开的通道；关闭时尝试所有通道并汇总 CleanupError。上下文中的原始异常不会被关闭异常覆盖。
- 不自动重试写操作；HealthService 仅轮询 GET 健康接口。timeout 是单次通信预算，HTTP/FTP 标准库超时是阻塞 I/O 超时，并非严格端到端截止时间；SSH/ADB subprocess 和串口 exchange 受总执行预算约束。
- 库仅使用标准 logging，不配置根 logger、不记录凭据或完整配置。结果内容由消费者决定是否落盘。
- 默认不提供跨进程设备锁。pytest-xdist 下应为 worker 分配不同物理设备，或在用例仓库实现实验室资源租约。
- FTP 下载失败可能留下部分本地文件，上传失败可能留下部分远端文件；固件烧录/升级流程应由产品服务实现校验及恢复逻辑。

## 框架验证

框架测试统一放在 `unittest/`，使用 pytest；该目录不要添加 `__init__.py`，以免与 Python 标准库 `unittest` 冲突。`engine/` 是通信实现的新目录，导入路径为 `embedded_test_framework.engine`；Transport 类名与 `register_transport()` 扩展接口保持不变。

| 测试文件 | 对应实现 |
| --- | --- |
| `test_engine.py` | engine/base、command、ftp、http、memory、serial |
| `test_devices.py` | devices/base 的能力路由和通道约束 |
| `test_hosts.py` | hosts/base、local，以及主机发现服务 |
| `test_services.py` | 系统、健康轮询、文件服务 |
| `test_config.py` | 配置校验、工厂与注册 |
| `test_errors.py` | 公共异常契约 |
| `test_pytest_plugin.py` | 独立进程中的 pytest fixture 初始化和释放 |
| `test_framework.py` | 跨模块回归、本地 HTTP、设备回滚、环境变量 |

```powershell
python -m pytest unittest
python -m pytest examples/external_tests --device-config examples/external_tests/devices.json
```

测试覆盖离线调用、真实本地 HTTP 请求、连接失败回滚、清理异常、配置环境变量、扩展注册、SSH 连接失败和串口超时。真实 SSH/ADB/串口/FTP 设备需在实验室集成验证。

## Jenkins

根目录 `Jenkinsfile` 使用 Declarative Pipeline，按检出、创建虚拟环境、单元测试、用例示例、wheel 构建顺序执行。测试失败仍发布 JUnit XML，成功后归档 wheel；不会发布到制品库或连接真实硬件。

Jenkins 节点需安装 Python 3.11+（Windows PATH 提供 `python`，Unix 提供 `python3`），能访问所需 Python 包源，并安装 Pipeline、Git 和 JUnit 插件。创建 Pipeline from SCM 或 Multibranch Pipeline，将脚本路径设为 `Jenkinsfile`。流水线检出前清理分配给任务的工作区，请使用专用 Jenkins 工作区。

本地生成同格式报告：`python -m pytest unittest --junitxml=reports/unit.xml`。流水线语法与报告步骤参考 [Jenkins Pipeline 文档](https://www.jenkins.io/doc/book/pipeline/syntax/) 和 [JUnit 步骤文档](https://www.jenkins.io/doc/pipeline/steps/junit/)。

实际 SSH 设备用例见 [device_tests/README.md](device_tests/README.md)，包括登录设备执行 uname -r 的运行说明。
