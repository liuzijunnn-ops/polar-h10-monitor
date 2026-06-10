# Polar H10 实时监控与 HRV 录制

基于 [polar-python](https://pypi.org/project/polar-python/) 和 [polar-display](https://github.com/zHElEARN/polar-display) 开发的 Polar H10 数据采集程序。

## 功能

- 实时显示 **ECG**（130 Hz）、**ACC**（25 Hz，三轴）波形，60 fps 刷新
- 波形保留完整历史，滚轮缩放 / 拖拽平移可查看全貌
- 实时显示心率、RR 间隔及 **HRV 时域 + 频域** 指标
- 点击按钮开始/停止录制，每次录制保存为独立会话
- 录制前可自定义会话文件夹名称（默认 `YYYYMMDD-HHMMSS`，与 polar-display 一致）

## 环境要求

- Python 3.10+
- macOS / Windows / Linux（需支持 BLE）
- Polar H10 心率带

## 安装

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

1. 打开 Polar H10（湿润电极贴片后佩戴）
2. 程序自动扫描并连接
3. 输入会话名称（可选），点击 **开始录制**
4. 再次点击 **停止录制**，数据自动保存

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

界面侧边栏：时域为最近 60 个 RR 的滚动窗口；频域需累积足够时长后显示。`hrv.json` 为整段录制的完整统计。
