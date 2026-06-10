"""HRV metrics (time-domain and frequency-domain) from RR intervals."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

# Task Force bands (Hz)
LF_BAND = (0.04, 0.15)
HF_BAND = (0.15, 0.4)
VLF_BAND = (0.0033, 0.04)

INTERP_FS = 4.0  # Hz, standard resampling rate for HRV spectral analysis
MIN_RR_FOR_FREQ = 30


@dataclass
class FreqHRVMetrics:
    lf_power_ms2: float
    hf_power_ms2: float
    lf_hf_ratio: float
    total_power_ms2: float
    vlf_power_ms2: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HRVMetrics:
    count: int
    mean_rr_ms: float
    mean_hr_bpm: float
    sdnn_ms: float
    rmssd_ms: float
    pnn50_pct: float
    min_rr_ms: float
    max_rr_ms: float
    median_rr_ms: float
    frequency: FreqHRVMetrics | None = field(default=None)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.frequency is None:
            d.pop("frequency", None)
        return d


def _band_power(freqs: np.ndarray, psd: np.ndarray, low: float, high: float) -> float:
    mask = (freqs >= low) & (freqs < high)
    if not np.any(mask):
        return 0.0
    return float(np.trapezoid(psd[mask], freqs[mask]))


def compute_freq_hrv(rr_intervals_ms: list[float], interp_fs: float = INTERP_FS) -> FreqHRVMetrics | None:
    """Compute frequency-domain HRV via interpolated tachogram + Welch PSD."""
    if len(rr_intervals_ms) < MIN_RR_FOR_FREQ:
        return None

    rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    rr = rr[np.isfinite(rr) & (rr > 0)]
    if len(rr) < MIN_RR_FOR_FREQ:
        return None

    # Beat times in seconds (cumulative RR)
    beat_times = np.cumsum(rr) / 1000.0
    duration = beat_times[-1]
    if duration < 60.0:
        return None

    t_uniform = np.arange(0, duration, 1.0 / interp_fs)
    rr_uniform = np.interp(t_uniform, beat_times, rr)

    # Detrend: remove linear trend
    rr_uniform = rr_uniform - np.linspace(rr_uniform[0], rr_uniform[-1], len(rr_uniform))

    nperseg = min(256, len(rr_uniform) // 2)
    if nperseg < 64:
        return None

    try:
        from scipy.signal import welch

        freqs, psd = welch(rr_uniform, fs=interp_fs, nperseg=nperseg, noverlap=nperseg // 2)
    except ImportError:
        # Fallback: single FFT segment
        window = np.hanning(len(rr_uniform))
        spec = np.fft.rfft(rr_uniform * window)
        psd = (np.abs(spec) ** 2) / (interp_fs * len(rr_uniform))
        freqs = np.fft.rfftfreq(len(rr_uniform), d=1.0 / interp_fs)

    vlf = _band_power(freqs, psd, VLF_BAND[0], VLF_BAND[1])
    lf = _band_power(freqs, psd, LF_BAND[0], LF_BAND[1])
    hf = _band_power(freqs, psd, HF_BAND[0], HF_BAND[1])
    total = _band_power(freqs, psd, VLF_BAND[0], HF_BAND[1])

    return FreqHRVMetrics(
        vlf_power_ms2=vlf,
        lf_power_ms2=lf,
        hf_power_ms2=hf,
        lf_hf_ratio=lf / hf if hf > 0 else 0.0,
        total_power_ms2=total,
    )


def compute_hrv(rr_intervals_ms: list[float], include_frequency: bool = True) -> HRVMetrics | None:
    """Compute time-domain HRV; optionally attach frequency-domain metrics."""
    if len(rr_intervals_ms) < 2:
        return None

    rr = np.asarray(rr_intervals_ms, dtype=np.float64)
    rr = rr[np.isfinite(rr) & (rr > 0)]
    if len(rr) < 2:
        return None

    diff = np.diff(rr)
    sdnn = float(np.std(rr, ddof=1))
    rmssd = float(np.sqrt(np.mean(diff**2)))
    pnn50 = float(np.sum(np.abs(diff) > 50) / len(diff) * 100)
    mean_rr = float(np.mean(rr))

    freq = compute_freq_hrv(list(rr)) if include_frequency else None

    return HRVMetrics(
        count=len(rr),
        mean_rr_ms=mean_rr,
        mean_hr_bpm=60000.0 / mean_rr,
        sdnn_ms=sdnn,
        rmssd_ms=rmssd,
        pnn50_pct=pnn50,
        min_rr_ms=float(np.min(rr)),
        max_rr_ms=float(np.max(rr)),
        median_rr_ms=float(np.median(rr)),
        frequency=freq,
    )


def save_hrv_json(metrics: HRVMetrics, path: Path) -> None:
    path.write_text(json.dumps(metrics.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
