# Polar H10 实时监控与 HRV 录制

参考 [polar-python](https://pypi.org/project/polar-python/) 和 [polar-display](https://github.com/zHElEARN/polar-display) 的使用方式开发；当前采集链路使用本项目内置的 Bleak/Polar PMD 协议实现，不再依赖 `polar-python` 连接设备。

## 功能

- 实时显示 **ECG**（130 Hz）、**ACC**（25 Hz，三轴）波形，60 fps 刷新
- 波形保留完整历史，滚轮缩放 / 拖拽平移可查看全貌
- 实时显示心率、RR 间隔及 **HRV 时域 + 频域** 指标
- 点击按钮开始/停止录制，每次录制保存为独立会话
- 录制前可自定义会话文件夹名称（默认 `YYYYMMDD-HHMMSS`，与 polar-display 一致）

## 环境要求

- Polar H10 心率带（湿润电极贴片后佩戴）
- 电脑支持蓝牙 BLE
- **方式 A（推荐）**：Windows 10/11 或 macOS，无需安装 Python
- **方式 B**：Python 3.10+（开发者 / Linux）

---

## 安装教程（普通用户 · 下载安装包）

### 1. 下载

打开 GitHub **Releases** 页面，下载对应系统的 zip：

| 系统 | 文件 |
|------|------|
| Windows | `PolarH10Monitor-Windows.zip` |
| macOS | `PolarH10Monitor-macOS.zip` |

> 若 Release 尚未生成：进入仓库 **Actions → Build**，等最新一次构建完成后，在 **Artifacts** 里下载 `PolarH10Monitor-Windows` 或 `PolarH10Monitor-macOS`。

### 2. 解压

将 zip 解压到任意目录，例如：

- Windows：`C:\Tools\PolarH10Monitor\`
- macOS：`~/Applications/PolarH10Monitor/`

解压后文件夹内应包含 `PolarH10Monitor.exe`（Windows）或 `PolarH10Monitor`（macOS）及依赖文件。**请保留整个文件夹**，不要只复制单个 exe。

### 3. 首次运行

**Windows**

1. 确认电脑蓝牙已开启
2. 双击 `PolarH10Monitor.exe`
3. 若 Windows 安全提示「未知发布者」，点 **更多信息 → 仍要运行**（开源未签名应用常见）

**macOS**

1. 确认蓝牙已开启
2. 首次运行若提示「无法验证开发者」：
   ```bash
   xattr -cr /路径/to/PolarH10Monitor
   ```
   或在 **系统设置 → 隐私与安全性** 中允许打开
3. 双击 `PolarH10Monitor` 运行

### 4. 使用

1. 打开 Polar H10，贴在胸口
2. 程序自动扫描并连接（顶部显示「已连接」）
3. （可选）修改顶部 **会话名称**
4. 点击 **开始录制** → 采集一段时间 → 点击 **停止录制**
5. 数据保存在程序**同级目录**的 `logs/<会话名>/` 下

### Windows 蓝牙排查

- 如果连接失败，先打开程序同级目录下的 `logs/app.log`，里面会记录 BLE 扫描到的设备名、地址、RSSI 和错误 traceback
- 确认 Polar H10 没有被手机 Polar Beat / Flow 或其他电脑占用；必要时关闭手机蓝牙或退出相关 App
- Windows 默认尝试完整 ECG/ACC/HR/RR 模式，和 macOS 使用同一套功能；程序会直接订阅 Polar PMD 控制/数据特征，不再通过 `polar-python`
- 如果 Windows 在打开 PMD 时出现 `Insufficient Authentication`、`操作已被用户取消` 或 GATT 超时，程序会尝试一次配对、断开、禁用缓存服务后重连并重试 PMD
- 若只想确认标准心率服务是否可用，可设置 `POLAR_STREAM_MODE=hr` 后启动；该诊断模式只显示心率/RR，不采集 ECG/ACC
- 如果日志里能看到设备但名称不完整，可在命令行设置设备名或地址片段后启动：
  ```bat
  set POLAR_DEVICE=Polar H10
  PolarH10Monitor.exe
  ```
- 如果 Windows 已经配对过但仍连接异常，可在系统蓝牙设置中删除该设备，重启蓝牙后再运行程序

### 5. 数据位置

```
PolarH10Monitor/          ← 程序所在文件夹
├── PolarH10Monitor.exe   （或 macOS 可执行文件）
└── logs/
    └── 20260610-120000/  ← 每次录制一个文件夹
        ├── raw/
        ├── csv/
        ├── hrv.json
        └── meta.json
```

---

## 安装教程（开发者 · 源码运行）

```bash
git clone https://github.com/liuzijunnn-ops/polar-h10-monitor.git
cd polar-h10-monitor
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 输出目录结构

```
logs/<会话名>/
├── raw/                  # 原始二进制数据
│   ├── ecg.npy
│   ├── ecg_timestamps.npy
│   ├── acc.npz
│   ├── rr.npz
│   └── hr.npz
├── csv/                  # CSV 导出
│   ├── ecg.csv
│   ├── acc.csv
│   ├── rr.csv
│   ├── hr.csv
│   └── hrv.csv
├── hrv.json              # HRV 汇总（时域 + 频域）
└── meta.json             # 会话元数据
```

## HRV 指标

**时域**（基于 RR 间隔）：

- SDNN、RMSSD、pNN50
- 平均 RR / HR、最小 / 最大 / 中位 RR

**频域**（录制 ≥60s 且 RR ≥30 时计算，Welch PSD）：

- VLF / LF / HF 功率（ms²）
- LF/HF 比值、总功率

界面侧边栏：时域为最近 60 个 RR 的滚动窗口；频域使用最近 150 个 RR，累积时长 ≥45s 后显示（下方有进度提示）。`hrv.json` 为整段录制的完整统计（频域要求 ≥60s）。

实时 HRV 只在录制期间累计和计算。开始录制和停止录制都会清空界面的 HRV 滚动窗口，停止后保持清零；下一次录制从第一个新 RR 开始重新累计，避免换人或中途空窗期间的历史 RR 混入指标。保存到 `hrv.json` 的结果也只使用本次录制期间采集到的 RR。

## 打包为可双击运行的程序

### GitHub Actions（推荐）

推送到 GitHub 后，在 **Actions** 页可下载构建产物：

- 推送到 `main` / 打 `v*` 标签 → 自动构建 Windows + macOS
- 手动触发：**Actions → Build → Run workflow**

打标签 `v1.0.0` 等会自动创建 [Release](https://github.com/liuzijunnn-ops/polar-h10-monitor/releases) 并附上 zip 安装包。

### 本地打包

**Windows：**

```bat
build_windows.bat
```

**macOS：**

```bash
chmod +x build_mac.sh && ./build_mac.sh
```

运行 `dist/PolarH10Monitor/` 下的可执行文件，`logs/` 保存在程序同级目录。
