# 安装准备

## 首次准备

1. 安装[Python 3.13](https://www.python.org/downloads/windows/)，包含pip和Python Launcher。安装脚本优先使用`py -3.13`，否则使用PATH中的`python`。
2. 安装Apple Devices或iTunes提供的USB设备支持组件，确保电脑能识别手机。已有可用驱动的电脑无需重复安装，参考[Apple连接排障](https://support.apple.com/en-us/108643)及[pymobiledevice3排障](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/troubleshooting.md)。不需要图形化虚拟定位软件。
3. 在手机“设置→隐私与安全→开发者模式”中开启开发者模式，按提示重启并再次确认。USB连接后解锁手机，按提示选择“信任”并输入密码。

## 安装依赖

双击本目录的`install.cmd`。脚本在项目根目录创建`.venv`并安装`requirements.txt`中的依赖，不修改全局Python环境，不自动安装Apple驱动或修改手机设置。

Python未在PATH中时，可手动指定解释器。以下命令在项目根目录执行，示例路径请替换为自己的Python安装路径：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File ".\setup\install.ps1" -Python "D:\Python313\python.exe"
```

执行策略设置只针对这一次PowerShell进程。安装脚本会检查Python版本、pip依赖和定位模块导入；安装失败会显示错误，不会报告成功。

安装完成后，双击根目录`打开工作台.cmd`。浏览器访问`http://127.0.0.1:18763`，仅本机可访问。

## 常见问题

- 下载失败：检查网络，重新执行安装脚本。已有环境会复用；不完整或搬迁后的环境需先停止程序、改名备份`.venv`再重新安装。
- 无法识别手机：检查数据线、解锁、信任提示及Apple服务，先确认Apple软件能够识别设备。
- 开发者连接失败：检查开发者模式。不同系统版本的隧道支持不同，参考[官方隧道说明](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)。首次连接可能还需联网获取开发者支持文件。
- 端口被占用：先在另一份工作台停止定位，再退出其后台服务。关闭浏览器不会关闭服务；可在任务管理器核对命令行，结束对应目录的`app.py`进程。
- 地图空白：检查CDN和底图网络访问，本项目未包含离线地图包。
- 定位回跳：检查`data/worker.log`及手机地图。提高频率不等于屏蔽真实位置，不保证消除回跳。

请仅连接一台目标设备，并先停止其他虚拟定位工具。本项目不会自动接管其他目录的私人定位脚本。
