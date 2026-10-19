# 导出数据格式

本说明对应仓库当前 `recorder.py`、`polar_ble.py`、`hrv.py` 的实现。这里的“原始”指解码并按录制条件接收的样本，不是未经处理的 BLE 原始字节流。GUI 会先过滤无效 RR；无效 RR 不保留在会话数据中。

## raw/ 与 csv/

| 文件 | NumPy 字段 / CSV 列 | 单位与含义 |
| --- | --- | --- |
| `ecg.npy` | 一维 int32 / `sample_uv` | ECG，µV |
| `ecg_timestamps.npy` | 一维 int64 / `timestamp_ns` | 对应 ECG 包时间戳，ns |
| `acc.npz` | `timestamps`, `x`, `y`, `z` / `timestamp_ns`, `x_mg`, `y_mg`, `z_mg` | 三轴 ACC，mg（1000 mg = 1 g） |
| `rr.npz` | `rr_intervals_ms`, `timestamps` / `rr_interval_ms`, `timestamp` | RR，ms；电脑接收时间，Unix 秒 |
| `hr.npz` | `heartrate_bpm`, `timestamps` / `heartrate_bpm`, `timestamp` | 心率，bpm；电脑接收时间，Unix 秒 |

CSV 第一列均为从 0 开始的 `index`。缺失的数据流不生成对应文件。`hrv.csv` 为 `metric,value,unit` 三列，与 `hrv.json` 汇总对应。

## 时间戳的限制

ECG / ACC 包中的设备时间以 2000-01-01 为原点；解析器给包时间加上 `946684800000000000 ns`，转换为 Unix 原点数值。**这只改变数值原点，不校准设备时钟**。录制器把同一个包时间重复给该包全部样本，因此时间戳有重复；不能直接用相邻两行的时间差估计采样周期。

HR / RR 时间来自电脑 `datetime.now().timestamp()`，是通知处理时间。同一条通知里的多个 RR 也共享一个时间，不能视为各心搏发生时刻。绘图横轴为样本索引。需要跨设备同步或精确样本时刻的研究，应另行验证设备时钟、包时间含义、丢包与插值方案。

`meta.json` 的起止时间是本机本地时间字符串，没有时区偏移；交换数据时请另外记录采集地点与时区。文件中的 130 / 25 Hz 是程序请求值，不是实际采样率测量结果。

## HRV 汇总

`hrv.json` 的主要字段：`count`, `mean_rr_ms`, `mean_hr_bpm`, `sdnn_ms`, `rmssd_ms`, `pnn50_pct`, `min_rr_ms`, `max_rr_ms`, `median_rr_ms`。平均 HR 为 `60000 / mean_rr_ms`，不是对接收到的 bpm 直接取平均。

满足有效 RR 数量与时长门槛时，才有嵌套 `frequency`：`vlf_power_ms2`, `lf_power_ms2`, `hf_power_ms2`, `lf_hf_ratio`, `total_power_ms2`。范围：VLF `[0.0033, 0.04)`、LF `[0.04, 0.15)`、HF `[0.15, 0.4)` Hz。HF 功率为 0 时，当前实现将 LF/HF 写为 0，**这不表示真实比值为零**，解读前须检查 HF。

SDNN 使用样本标准差（`ddof=1`）；pNN50 使用相邻有效 RR 差值绝对值 **大于** 50 ms 的比例。过滤后直接拼接保留的 RR，没有补回被删心搏的时间；这会影响频谱。短时或运动伪迹明显的数据应先独立检查，不能把自动汇总直接当成验证后的结果。

## Python 读取

```python
from pathlib import Path
import json
import numpy as np

session = Path('logs/session_001_sitting')
ecg_file = session / 'raw' / 'ecg.npy'
if ecg_file.exists():
    ecg_uv = np.load(ecg_file, allow_pickle=False)
    print('ECG samples:', len(ecg_uv))

rr_file = session / 'raw' / 'rr.npz'
if rr_file.exists():
    with np.load(rr_file, allow_pickle=False) as rr:
        print(rr['rr_intervals_ms'][:10])

meta = json.loads((session / 'meta.json').read_text(encoding='utf-8'))
print(meta)
```

会话名称决定目录路径。当前未进行名称合法性与同名冲突校验，请使用唯一的单层目录名，避免覆盖历史数据。仓库不附真实被试数据。
