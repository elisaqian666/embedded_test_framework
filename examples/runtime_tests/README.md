# 独立测试仓库示例

将本目录整体复制到独立仓库，安装框架后运行：

```powershell
python -m pip install -e "D:/work_project/embedded_test_framework[test]"
python -m pytest --device-config devices.json
```

在框架仓库内也可直接运行：

```powershell
python -m pytest examples/runtime_tests --device-config examples/runtime_tests/devices.json
```

这个示例完全离线。两个设备分别返回 ifconfig 文本和产品 JSON，测试都调用同一个
`NetworkService.get_ipv4_addresses()`。产品命令只出现在 `product_adapters.py` 和模拟配置中。

`conftest.py` 显式注册适配器，不需要修改框架；模拟 Helper 展示实验室资源的准备和恢复。
断言失败时 pytest 插件自动收集支持的日志/崩溃信息，并在测试报告中写入证据清单路径。
性能数据保存为 JSONL，是否超标由测试用例判断。

连接真实设备时，把对应 `memory` 通道替换为 `ssh` / `adb` / 产品协议适配器，
并为真实设备注册匹配的 Capability；示例日志命令和指标命令不是通用设备命令。
