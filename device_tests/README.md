# 实际设备测试

此目录放需要真实硬件的用例，不在默认单元测试或 Jenkins 离线测试范围内。

`test_kernel_version.py` 通过框架 SSH 登录 `192.168.1.103`（用户 `root`），执行 `uname -r`，检查命令成功且内核版本非空。设备退出或断言失败都会关闭 SSH 会话。

在项目根目录执行 PowerShell：

```powershell
python -m pip install -e ".[test,ssh]"
# 首次使用前，通过可信渠道核对主机指纹，并用 OpenSSH 保存主机密钥。
ssh root@192.168.1.103
# 登录后输入 exit 返回本机。
$env:DUT_SSH_PASSWORD = 'letmein'
python -m pytest device_tests/test_kernel_version.py -v -s
Remove-Item Env:DUT_SSH_PASSWORD
```

密码通过环境变量传入，不写入测试代码。SSH 使用本机 known_hosts 校验设备身份；缺失或不匹配的主机密钥会使连接失败。未设置密码时测试跳过。
