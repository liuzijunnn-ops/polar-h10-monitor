"""Session recording and file export for Polar H10 data."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np

from hrv import HRVMetrics, compute_hrv, save_hrv_json

LOGS_DIR = Path("logs")
RAW_DIR = "raw"
CSV_DIR = "csv"

ECG_SAMPLE_RATE = 130
ACC_SAMPLE_RATE = 25


@dataclass
class SessionRecorder:
    recording: bool = False
    session_name: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None

    ecg_timestamps: list[int] = field(default_factory=list)
    ecg_samples: list[int] = field(default_factory=list)

    acc_timestamps: list[int] = field(default_factory=list)
    acc_x: list[int] = field(default_factory=list)
    acc_y: list[int] = field(default_factory=list)
    acc_z: list[int] = field(default_factory=list)

    heartrate_values: list[int] = field(default_factory=list)
    heartrate_timestamps: list[float] = field(default_factory=list)
    rr_intervals: list[float] = field(default_factory=list)
    rr_timestamps: list[float] = field(default_factory=list)

    def start(self, session_name: str) -> None:
        self.clear()
        self.recording = True
        self.session_name = session_name
        self.started_at = datetime.now()

    def stop(self) -> Path:
        self.recording = False
        self.ended_at = datetime.now()
        return self.save()

    def clear(self) -> None:
        self.ecg_timestamps.clear()
        self.ecg_samples.clear()
        self.acc_timestamps.clear()
        self.acc_x.clear()
        self.acc_y.clear()
        self.acc_z.clear()
        self.heartrate_values.clear()
        self.heartrate_timestamps.clear()
        self.rr_intervals.clear()
        self.rr_timestamps.clear()
        self.started_at = None
        self.ended_at = None

    def add_ecg(self, timestamp: int, samples: list[int]) -> None:
        if not self.recording:
            return
        self.ecg_timestamps.extend([timestamp] * len(samples))
        self.ecg_samples.extend(samples)

    def add_acc(self, timestamp: int, samples: list[tuple[int, int, int]]) -> None:
        if not self.recording:
            return
        self.acc_timestamps.extend([timestamp] * len(samples))
        for x, y, z in samples:
            self.acc_x.append(x)
            self.acc_y.append(y)
            self.acc_z.append(z)

    def add_hr(self, heartrate: int, rr_intervals: list[float]) -> None:
        if not self.recording:
            return
        now = datetime.now().timestamp()
        self.heartrate_values.append(heartrate)
        self.heartrate_timestamps.append(now)
        for rr in rr_intervals:
            self.rr_intervals.append(rr)
            self.rr_timestamps.append(now)

    def _save_raw(self, raw_folder: Path) -> None:
        if self.ecg_samples:
            np.save(raw_folder / "ecg.npy", np.asarray(self.ecg_samples, dtype=np.int32))
            np.save(raw_folder / "ecg_timestamps.npy", np.asarray(self.ecg_timestamps, dtype=np.int64))

        if self.acc_x:
            np.savez(
                raw_folder / "acc.npz",
                timestamps=np.asarray(self.acc_timestamps, dtype=np.int64),
                x=np.asarray(self.acc_x, dtype=np.int32),
                y=np.asarray(self.acc_y, dtype=np.int32),
                z=np.asarray(self.acc_z, dtype=np.int32),
            )

        if self.rr_intervals:
            np.savez(
                raw_folder / "rr.npz",
                rr_intervals_ms=np.asarray(self.rr_intervals, dtype=np.float64),
                timestamps=np.asarray(self.rr_timestamps, dtype=np.float64),
            )

        if self.heartrate_values:
            np.savez(
                raw_folder / "hr.npz",
                heartrate_bpm=np.asarray(self.heartrate_values, dtype=np.int32),
                timestamps=np.asarray(self.heartrate_timestamps, dtype=np.float64),
            )

    def _save_csv(self, csv_folder: Path) -> None:
        if self.ecg_samples:
            with (csv_folder / "ecg.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["index", "timestamp_ns", "sample_uv"])
                for i, (ts, val) in enumerate(zip(self.ecg_timestamps, self.ecg_samples)):
                    writer.writerow([i, ts, val])

        if self.acc_x:
            with (csv_folder / "acc.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["index", "timestamp_ns", "x_mg", "y_mg", "z_mg"])
                for i, (ts, x, y, z) in enumerate(
                    zip(self.acc_timestamps, self.acc_x, self.acc_y, self.acc_z)
                ):
                    writer.writerow([i, ts, x, y, z])

        if self.rr_intervals:
            with (csv_folder / "rr.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["index", "timestamp", "rr_interval_ms"])
                for i, (ts, rr) in enumerate(zip(self.rr_timestamps, self.rr_intervals)):
                    writer.writerow([i, ts, rr])

        if self.heartrate_values:
            with (csv_folder / "hr.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["index", "timestamp", "heartrate_bpm"])
                for i, (ts, hr) in enumerate(zip(self.heartrate_timestamps, self.heartrate_values)):
                    writer.writerow([i, ts, hr])

    def _save_hrv_csv(self, csv_folder: Path, hrv: HRVMetrics) -> None:
        with (csv_folder / "hrv.csv").open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value", "unit"])
            rows = [
                ("count", hrv.count, "beats"),
                ("mean_rr_ms", f"{hrv.mean_rr_ms:.4f}", "ms"),
                ("mean_hr_bpm", f"{hrv.mean_hr_bpm:.4f}", "bpm"),
                ("sdnn_ms", f"{hrv.sdnn_ms:.4f}", "ms"),
                ("rmssd_ms", f"{hrv.rmssd_ms:.4f}", "ms"),
                ("pnn50_pct", f"{hrv.pnn50_pct:.4f}", "%"),
                ("min_rr_ms", f"{hrv.min_rr_ms:.4f}", "ms"),
                ("max_rr_ms", f"{hrv.max_rr_ms:.4f}", "ms"),
                ("median_rr_ms", f"{hrv.median_rr_ms:.4f}", "ms"),
            ]
            if hrv.frequency:
                rows.extend([
                    ("vlf_power_ms2", f"{hrv.frequency.vlf_power_ms2:.4f}", "ms²"),
                    ("lf_power_ms2", f"{hrv.frequency.lf_power_ms2:.4f}", "ms²"),
                    ("hf_power_ms2", f"{hrv.frequency.hf_power_ms2:.4f}", "ms²"),
                    ("lf_hf_ratio", f"{hrv.frequency.lf_hf_ratio:.4f}", ""),
                    ("total_power_ms2", f"{hrv.frequency.total_power_ms2:.4f}", "ms²"),
                ])
            writer.writerows(rows)

    def save(self) -> Path:
        folder = LOGS_DIR / self.session_name
        raw_folder = folder / RAW_DIR
        csv_folder = folder / CSV_DIR
        raw_folder.mkdir(parents=True, exist_ok=True)
        csv_folder.mkdir(parents=True, exist_ok=True)

        self._save_raw(raw_folder)
        self._save_csv(csv_folder)

        hrv: HRVMetrics | None = compute_hrv(self.rr_intervals, include_frequency=True)
        if hrv:
            save_hrv_json(hrv, folder / "hrv.json")
            self._save_hrv_csv(csv_folder, hrv)

        meta = {
            "session_name": self.session_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "ecg_sample_rate_hz": ECG_SAMPLE_RATE,
            "acc_sample_rate_hz": ACC_SAMPLE_RATE,
            "ecg_samples": len(self.ecg_samples),
            "acc_samples": len(self.acc_x),
            "rr_count": len(self.rr_intervals),
            "hr_count": len(self.heartrate_values),
            "paths": {"raw": RAW_DIR, "csv": CSV_DIR},
        }
        (folder / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        return folder


def default_session_name() -> str:
    """Same naming convention as polar-display: YYYYMMDD-HHMMSS."""
    return datetime.now().strftime("%Y%m%d-%H%M%S")
