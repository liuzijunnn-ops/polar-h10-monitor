# Polar H10 Monitor

[![Build](https://github.com/liuzijunnn-ops/polar-h10-monitor/actions/workflows/build.yml/badge.svg)](https://github.com/liuzijunnn-ops/polar-h10-monitor/actions/workflows/build.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**用电脑通过蓝牙接收 Polar H10 数据，实时查看 ECG / ACC 波形、心率与 HRV，并按会话导出数据。**

这是基于 Python、PyQt6 和 Bleak 的本地桌面应用，主要面向运动数据采集、教学与研究原型。界面为中文，数据保存在本机。本项目参考并改编了 [polar-python](https://github.com/zHElEARN/polar-python) 的部分协议解析代码，并参考 [polar-display](https://github.com/zHElEARN/polar-display) 的展示与录制流程；详见[来源与许可证](THIRD_PARTY_NOTICES.md)。本项目与 Polar 公司无隶属或官方认证关系。

## 功能

| 数据 / 功能 | 当前实现 |
| --- | --- |
| ECG 心电 | 请求 130 Hz、14 bit，显示与保存 µV 样本 |
| ACC 加速度 | 请求 25 Hz、16 bit、±2 g，显示与保存三轴 mg 样本 |
| HR / RR | 标准 BLE Heart Rate Service，bpm / ms |
| HRV 时域 | 平均 RR、平均 HR、SDNN、RMSSD、pNN50 等 |
| HRV 频域 | 插值 RR 序列、Welch PSD，计算 VLF / LF / HF 与 LF/HF |
| 会话录制 | 自定义名称、10 秒稳定等待、开始 / 停止、会话间清空缓冲 |
| 导出 | NumPy `.npy` / `.npz`、CSV、HRV JSON、会话元数据 |
| 波形浏览 | 保留本次会话全部历史，滚轮缩放、拖拽平移 |

当前采集链路由 `polar_ble.py` 通过 Bleak 直接连接设备，不再依赖 `polar-python` 包。仅实现单台 H10 的采集；不会同时录制多台设备。显示定时器约 60 fps，不代表蓝牙采样率或实际刷新性能保证。

## 快速开始：源码运行

需要 Polar H10 胸带、支持 BLE 的电脑、Python **3.10+**。自动构建使用 Python 3.11；建议优先使用 3.11。Windows / macOS 有构建流程；Linux 源码运行需要 BlueZ 和图形桌面，尚未完成本项目实机验证。

1. 湿润胸带电极，扣上 H10 并佩戴；打开电脑蓝牙。
2. 退出可能占用设备的手机应用或其他采集程序。
3. 克隆项目并安装依赖：

```bash
git clone https://github.com/liuzijunnn-ops/polar-h10-monitor.git
cd polar-h10-monitor
```

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

**Windows PowerShell**（无需修改脚本执行策略）

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

macOS 首次运行时允许 Python / Terminal 访问蓝牙。若系统未弹出授权或权限被拒绝，在“系统设置 → 隐私与安全性 → 蓝牙”检查相应程序权限。

## 录制步骤

1. 启动后程序扫描约 12 秒，默认选择第一台名称包含 `Polar H10` 的设备。
2. 等待状态栏显示“数据流已启动”。此时尚未保存数据，波形与 HRV 要在开始录制后才更新。
3. 填写**新的、唯一的会话名称**，例如 `session_001_sitting`。只用文件夹名，不要填写路径、`..`、斜杠或反斜杠；当前版本不会阻止重名覆盖。
4. 点击“开始录制”，等待 **10 秒稳定倒计时**。倒计时内的数据会丢弃。
5. 观察 ECG / ACC 波形、心率、RR 与 HRV。没有 RR 时，不会生成 HRV；不要把空白指标当成 0。
6. 点击“停止录制”，等待“录制完成”弹窗并核对保存路径、样本数和文件。
7. 下一次录制会清空波形和 HRV 缓冲，再等待 10 秒。停止期间保持 BLE 连接，但不累计数据。

倒计时内再次点击停止会取消本次录制，不保存会话。正常录制时关闭窗口会询问是否保存后退出。数据在停止或正常退出时写盘，**强制结束进程或断电可能丢失尚未保存的会话**。长时间录制会持续增加内存占用，建议分段采集并检查文件。

## 数据保存位置

- 源码运行：项目目录下 `logs/<会话名>/`。
- 打包运行：可执行文件同级的 `logs/<会话名>/`，请放在可写目录。
- 运行日志：`logs/app.log`，可能包含附近蓝牙设备名称、地址与部分数据包；报告问题前请脱敏。

```text
logs/session_001_sitting/
├── raw/
│   ├── ecg.npy
│   ├── ecg_timestamps.npy
│   ├── acc.npz
│   ├── rr.npz
│   └── hr.npz
├── csv/
│   ├── ecg.csv
│   ├── acc.csv
│   ├── rr.csv
│   ├── hr.csv
│   └── hrv.csv
├── hrv.json
└── meta.json
```

只有实际收到的数据流才生成对应文件；HRV 至少需要两个有效 RR，频域还需要满足时长条件。字段、单位、时间戳含义和读取示例见[数据格式说明](docs/DATA_FORMAT.md)。

**时间戳边界：** ECG / ACC 保存的是设备数据包时间戳，同一包内的样本共享该时间戳；HR / RR 使用电脑收到通知的时间。程序没有执行设备与电脑时钟同步，也没有重建逐样本时间。不要将导出列直接视为经过验证的跨设备同步时间。

## HRV 的计算范围

| 位置 | 使用的数据 | 频域门槛 |
| --- | --- | --- |
| 实时侧栏时域 | 最近 60 个有效 RR | 不适用 |
| 实时侧栏频域 | 最近 150 个有效 RR | 至少 30 个 RR，累积 RR 时长 ≥45 秒 |
| 保存的 HRV 汇总 | 本次会话全部有效 RR | 至少 30 个 RR，累积 RR 时长 ≥60 秒 |

RR 只经过有限值和 `300–2000 ms` 范围筛选，超出范围的 RR 不进入 GUI 录制文件或 HRV；这不是完整的异位搏动识别或运动伪迹校正。频域使用 4 Hz 插值与 Welch PSD；代码中的显示门槛只是实现条件，不表示已经满足正式 HRV 研究的记录时长或质量要求。短记录尤其不适合解读 VLF。本软件未完成独立心电参照验证，不用于医学诊断。

## 蓝牙排障与高级选项

- **找不到设备：** 检查佩戴、电极湿润、蓝牙距离、电池和其他程序占用。当前没有设备选择列表；多设备环境下建议指定 `POLAR_DEVICE`。
- **已连接但没有波形：** 先确认已点击开始录制并完成稳定倒计时，再看样本计数；“已连接”本身不代表所有数据流已经启动。
- **macOS `Peer removed pairing information` / Code=14：** 退出程序，在“系统设置 → 蓝牙”忽略该 H10，关闭再打开蓝牙，再佩戴并启动程序。让程序建立 BLE 连接。
- **Windows `Insufficient Authentication` / GATT 超时：** 程序会尝试配对、断开及重连一次。仍失败时删除系统中旧配对，重启蓝牙，检查是否被其他应用占用。
- **连接中断：** 当前没有自动重连；先停止并保存会话，再退出重开。检查样本数和信号连续性。
- **HR 正常但无 RR：** HRV 需要胸带发出的 RR 字段；检查设备状态与日志，HR 值本身不能替代 RR。

| 环境变量 | 值与含义 |
| --- | --- |
| `POLAR_DEVICE` | 设备名称或地址片段，大小写不敏感；匹配不到时仍会回退选择第一台 H10，务必核对状态栏设备名 |
| `POLAR_STREAM_MODE` | `full` 默认：ECG / ACC / HR / RR；`hr` 或 `hr-only`：仅 HR / RR；`auto`：完整采集失败后尝试 HR / RR |

macOS / Linux：

```bash
POLAR_DEVICE='Polar H10' POLAR_STREAM_MODE=hr python main.py
```

Windows PowerShell：

```powershell
$env:POLAR_DEVICE = 'Polar H10'
$env:POLAR_STREAM_MODE = 'hr'
.\.venv\Scripts\python.exe main.py
```

HR 模式不会采集 ECG / ACC，适合检查标准心率服务；`auto` 回退时也可能没有 ECG / ACC。诊断结束后删除该环境变量或改为 `full`。

## 可执行程序与构建

[Releases](https://github.com/liuzijunnn-ops/polar-h10-monitor/releases) 中的旧版本只对应各自标签，不一定包含当前源码的修复。需要当前实现时请源码运行，或从最近成功的 [Build 工作流](https://github.com/liuzijunnn-ops/polar-h10-monitor/actions/workflows/build.yml) 下载对应提交的构建产物。**构建成功不等于在你的蓝牙硬件上完成实测。**

保留解压后的整个文件夹及 `_internal` 内容，不要只复制 `.exe` 或主程序；macOS / Linux 解压若丢失执行权限，可执行 `chmod +x PolarH10Monitor`，再从终端运行。打包程序未签名或公证，系统可能拦截；也可选择源码运行。

本地打包：

```bash
# macOS
bash build_mac.sh
```

```bat
:: Windows（命令提示符）
build_windows.bat
```

输出在 `dist/PolarH10Monitor/`。GitHub Actions 会测试后构建 Windows / macOS；`v*` 标签会触发 Release。macOS 构建只对应 runner 的 CPU 架构，不是 Universal 通用包。打包附带 README、GPL、上游 MIT 通知与依赖许可证清单；分发前应检查第三方许可要求。

## 开发与验证

```bash
python -m unittest discover -s tests -v
```

测试只使用合成协议包、合成 RR 与临时目录，检查解析、HRV、会话隔离和文件导出；不会连接真实设备，也不证明实际采样率、测量精度或平台 BLE 稳定性。欢迎通过 [Issues](https://github.com/liuzijunnn-ops/polar-h10-monitor/issues) 反馈，附系统、Python 版本、提交版本、复现步骤与脱敏日志。请勿上传个人生理数据或设备标识。

## 开源来源与许可证

- [polar-python — zHElEARN / Zachary Liu](https://github.com/zHElEARN/polar-python)：早期采集依赖，也是当前部分 PMD 常量、帧结构及差分解析的参考与改编来源（MIT）。
- [polar-display — zHElEARN / Zachary Liu](https://github.com/zHElEARN/polar-display)：实时 ECG / ACC 展示、会话录制与文件组织的参考项目（MIT）。
- [Bleak](https://github.com/hbldh/bleak)、[NumPy](https://numpy.org/)、[SciPy](https://scipy.org/)、[PyQt6](https://www.riverbankcomputing.com/software/pyqt/)、[pyqtgraph](https://www.pyqtgraph.org/)：运行依赖。

本项目整体以 **GNU GPL v3.0** 发布，见 [LICENSE](LICENSE)。选择 GPLv3 与使用的开源 PyQt6 许可证保持兼容；上游 MIT 部分保留原作者版权与许可，不能仅以“引用链接”代替。详细来源、许可证原文和依赖关系见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [licenses/](licenses/)。
