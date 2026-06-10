"""PyQt6 GUI for real-time Polar H10 monitoring and recording."""

from __future__ import annotations

from collections import deque
from datetime import datetime

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from device_worker import PolarWorker
from hrv import compute_hrv
from polar_python.models import ACCData, ECGData, HRData
from recorder import ACC_SAMPLE_RATE, ECG_SAMPLE_RATE, LOGS_DIR, SessionRecorder, default_session_name

RR_WINDOW = 60
PLOT_REFRESH_MS = 16  # ~60 fps display refresh
ECG_SAMPLE_RATE_HZ = ECG_SAMPLE_RATE
ACC_SAMPLE_RATE_HZ = ACC_SAMPLE_RATE


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Polar H10 实时监控与录制")
        self.resize(1280, 800)

        pg.setConfigOptions(antialias=True)

        self.recorder = SessionRecorder()
        self.worker = PolarWorker()

        # Full session history — no maxlen, zoom out to see everything
        self._ecg_buffer: list[int] = []
        self._acc_x: list[int] = []
        self._acc_y: list[int] = []
        self._acc_z: list[int] = []
        self._rr_window: deque[float] = deque(maxlen=RR_WINDOW)

        self._ecg_dirty = False
        self._acc_dirty = False

        self._build_ui()
        self._connect_signals()
        self._setup_plots()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_plots)
        self._refresh_timer.start(PLOT_REFRESH_MS)

        self.worker.start()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        self.status_label = QLabel("初始化中...")
        self.status_label.setStyleSheet("color: #888;")
        toolbar.addWidget(self.status_label)
        toolbar.addStretch()

        toolbar.addWidget(QLabel("会话名称:"))
        self.session_input = QLineEdit(default_session_name())
        self.session_input.setPlaceholderText("默认: YYYYMMDD-HHMMSS")
        self.session_input.setMinimumWidth(220)
        toolbar.addWidget(self.session_input)

        self.record_btn = QPushButton("开始录制")
        self.record_btn.setCheckable(True)
        self.record_btn.setMinimumWidth(120)
        self.record_btn.setStyleSheet(
            "QPushButton { background: #2e7d32; color: white; padding: 8px 16px; font-weight: bold; }"
            "QPushButton:checked { background: #c62828; }"
        )
        self.record_btn.clicked.connect(self._toggle_recording)
        toolbar.addWidget(self.record_btn)

        root.addLayout(toolbar)

        content = QHBoxLayout()
        root.addLayout(content, stretch=1)

        charts = QVBoxLayout()
        content.addLayout(charts, stretch=4)

        self.ecg_plot = pg.PlotWidget(title=f"ECG (μV) — {ECG_SAMPLE_RATE_HZ} Hz | 滚轮缩放 / 拖拽平移")
        self.ecg_plot.setBackground("#1e1e1e")
        self.ecg_plot.showGrid(x=True, y=True, alpha=0.3)
        charts.addWidget(self.ecg_plot, stretch=1)

        self.acc_plot = pg.PlotWidget(title=f"ACC (mG) — {ACC_SAMPLE_RATE_HZ} Hz | 滚轮缩放 / 拖拽平移")
        self.acc_plot.setBackground("#1e1e1e")
        self.acc_plot.showGrid(x=True, y=True, alpha=0.3)
        self.acc_plot.addLegend(offset=(10, 10))
        charts.addWidget(self.acc_plot, stretch=1)

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setMaximumWidth(280)
        side_widget = QWidget()
        side = QVBoxLayout(side_widget)

        hr_box = QGroupBox("心率")
        hr_layout = QGridLayout(hr_box)
        self.hr_value = QLabel("--")
        self.hr_value.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self.hr_value.setStyleSheet("color: #ff5252;")
        hr_layout.addWidget(QLabel("BPM"), 0, 0)
        hr_layout.addWidget(self.hr_value, 0, 1)

        self.rr_value = QLabel("--")
        self.rr_value.setFont(QFont("Arial", 20))
        hr_layout.addWidget(QLabel("最新 RR (ms)"), 1, 0)
        hr_layout.addWidget(self.rr_value, 1, 1)
        side.addWidget(hr_box)

        hrv_box = QGroupBox("HRV 时域 (滚动窗口)")
        hrv_layout = QGridLayout(hrv_box)
        self.hrv_labels: dict[str, QLabel] = {}
        time_metrics = [
            ("mean_rr_ms", "平均 RR (ms)"),
            ("mean_hr_bpm", "平均 HR (BPM)"),
            ("sdnn_ms", "SDNN (ms)"),
            ("rmssd_ms", "RMSSD (ms)"),
            ("pnn50_pct", "pNN50 (%)"),
            ("count", "RR 数量"),
        ]
        for row, (key, label) in enumerate(time_metrics):
            hrv_layout.addWidget(QLabel(label), row, 0)
            value = QLabel("--")
            self.hrv_labels[key] = value
            hrv_layout.addWidget(value, row, 1)
        side.addWidget(hrv_box)

        freq_box = QGroupBox("HRV 频域 (≥60s 数据)")
        freq_layout = QGridLayout(freq_box)
        self.freq_labels: dict[str, QLabel] = {}
        freq_metrics = [
            ("lf_power_ms2", "LF (ms²)"),
            ("hf_power_ms2", "HF (ms²)"),
            ("lf_hf_ratio", "LF/HF"),
            ("total_power_ms2", "总功率 (ms²)"),
        ]
        for row, (key, label) in enumerate(freq_metrics):
            freq_layout.addWidget(QLabel(label), row, 0)
            value = QLabel("--")
            self.freq_labels[key] = value
            freq_layout.addWidget(value, row, 1)
        side.addWidget(freq_box)

        rec_box = QGroupBox("录制状态")
        rec_layout = QVBoxLayout(rec_box)
        self.rec_status = QLabel("未录制")
        self.rec_status.setStyleSheet("color: #888;")
        rec_layout.addWidget(self.rec_status)
        self.rec_duration = QLabel("时长: 00:00")
        rec_layout.addWidget(self.rec_duration)
        self.rec_samples = QLabel("样本: ECG 0 | ACC 0 | RR 0")
        self.rec_samples.setWordWrap(True)
        rec_layout.addWidget(self.rec_samples)
        self.buffer_info = QLabel("缓冲: ECG 0 | ACC 0")
        self.buffer_info.setWordWrap(True)
        self.buffer_info.setStyleSheet("color: #888; font-size: 11px;")
        rec_layout.addWidget(self.buffer_info)
        side.addWidget(rec_box)
        side.addStretch()

        side_scroll.setWidget(side_widget)
        content.addWidget(side_scroll, stretch=1)

        self.setStyleSheet(
            "QMainWindow, QWidget { background: #121212; color: #e0e0e0; }"
            "QGroupBox { border: 1px solid #333; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; }"
            "QLineEdit { background: #2a2a2a; border: 1px solid #444; padding: 4px; color: #eee; }"
            "QScrollArea { border: none; background: #121212; }"
        )

    def _setup_plots(self) -> None:
        for plot in (self.ecg_plot, self.acc_plot):
            plot.setMouseEnabled(x=True, y=True)
            plot.showButtons()
            vb = plot.getViewBox()
            vb.setMouseMode(pg.ViewBox.PanMode)
            vb.enableAutoRange(axis="y", enable=False)

        self.ecg_curve = self.ecg_plot.plot(pen=pg.mkPen("#00e676", width=1))
        self.ecg_curve.setClipToView(True)
        self.ecg_curve.setDownsampling(auto=True, method="peak")

        self.acc_x_curve = self.acc_plot.plot(pen=pg.mkPen("#ff9e80", width=1), name="X")
        self.acc_y_curve = self.acc_plot.plot(pen=pg.mkPen("#80d8ff", width=1), name="Y")
        self.acc_z_curve = self.acc_plot.plot(pen=pg.mkPen("#b388ff", width=1), name="Z")
        for curve in (self.acc_x_curve, self.acc_y_curve, self.acc_z_curve):
            curve.setClipToView(True)
            curve.setDownsampling(auto=True, method="peak")

        # Default view: latest ~10 s of ECG / ~30 s of ACC
        self._ecg_view_samples = ECG_SAMPLE_RATE_HZ * 10
        self._acc_view_samples = ACC_SAMPLE_RATE_HZ * 30

    def _connect_signals(self) -> None:
        self.worker.ecg_received.connect(self._on_ecg)
        self.worker.acc_received.connect(self._on_acc)
        self.worker.hr_received.connect(self._on_hr)
        self.worker.status_changed.connect(self._on_status)
        self.worker.connected.connect(self._on_connected)
        self.worker.error.connect(self._on_error)

    def _on_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _on_connected(self, name: str) -> None:
        self.status_label.setText(f"已连接: {name}")
        self.status_label.setStyleSheet("color: #66bb6a;")

    def _on_error(self, text: str) -> None:
        self.status_label.setText(text)
        self.status_label.setStyleSheet("color: #ef5350;")
        QMessageBox.warning(self, "连接错误", text)

    def _on_ecg(self, data: ECGData) -> None:
        self._ecg_buffer.extend(data.data)
        self._ecg_dirty = True
        self.recorder.add_ecg(data.timestamp, data.data)

    def _on_acc(self, data: ACCData) -> None:
        for x, y, z in data.data:
            self._acc_x.append(x)
            self._acc_y.append(y)
            self._acc_z.append(z)
        self._acc_dirty = True
        self.recorder.add_acc(data.timestamp, data.data)

    def _on_hr(self, data: HRData) -> None:
        self.hr_value.setText(str(data.heartrate))
        if data.rr_intervals:
            latest_rr = data.rr_intervals[-1]
            self.rr_value.setText(f"{latest_rr:.0f}")
            for rr in data.rr_intervals:
                self._rr_window.append(rr)
            self._update_hrv_display()
        self.recorder.add_hr(data.heartrate, data.rr_intervals)

    def _update_hrv_display(self) -> None:
        metrics = compute_hrv(list(self._rr_window), include_frequency=len(self._rr_window) >= 30)
        if not metrics:
            return
        for key, label in self.hrv_labels.items():
            value = getattr(metrics, key)
            if key == "count":
                label.setText(str(value))
            elif key == "pnn50_pct":
                label.setText(f"{value:.1f}")
            else:
                label.setText(f"{value:.1f}")

        if metrics.frequency:
            for key, label in self.freq_labels.items():
                value = getattr(metrics.frequency, key)
                label.setText(f"{value:.2f}")
        else:
            for label in self.freq_labels.values():
                label.setText("--")

    def _is_view_at_tail(self, plot: pg.PlotWidget, total: int, margin: float = 0.05) -> bool:
        """True if the visible x-range is near the latest samples (user hasn't panned away)."""
        x0, x1 = plot.getViewBox().viewRange()[0]
        return x1 >= total * (1.0 - margin)

    def _refresh_plots(self) -> None:
        if self._ecg_dirty and self._ecg_buffer:
            n = len(self._ecg_buffer)
            xs = np.arange(n, dtype=np.float64)
            self.ecg_curve.setData(xs, np.asarray(self._ecg_buffer, dtype=np.float32))
            if self._is_view_at_tail(self.ecg_plot, n):
                start = max(0, n - self._ecg_view_samples)
                self.ecg_plot.setXRange(start, n, padding=0.02)
            self._ecg_dirty = False

        if self._acc_dirty and self._acc_x:
            n = len(self._acc_x)
            xs = np.arange(n, dtype=np.float64)
            arr_x = np.asarray(self._acc_x, dtype=np.float32)
            arr_y = np.asarray(self._acc_y, dtype=np.float32)
            arr_z = np.asarray(self._acc_z, dtype=np.float32)
            self.acc_x_curve.setData(xs, arr_x)
            self.acc_y_curve.setData(xs, arr_y)
            self.acc_z_curve.setData(xs, arr_z)
            if self._is_view_at_tail(self.acc_plot, n):
                start = max(0, n - self._acc_view_samples)
                self.acc_plot.setXRange(start, n, padding=0.02)
            self._acc_dirty = False

        self.buffer_info.setText(
            f"缓冲: ECG {len(self._ecg_buffer)} ({len(self._ecg_buffer) / ECG_SAMPLE_RATE_HZ:.1f}s) | "
            f"ACC {len(self._acc_x)} ({len(self._acc_x) / ACC_SAMPLE_RATE_HZ:.1f}s)"
        )

        if self.recorder.recording and self.recorder.started_at:
            elapsed = datetime.now() - self.recorder.started_at
            mins, secs = divmod(int(elapsed.total_seconds()), 60)
            self.rec_duration.setText(f"时长: {mins:02d}:{secs:02d}")
            self.rec_samples.setText(
                f"样本: ECG {len(self.recorder.ecg_samples)} | "
                f"ACC {len(self.recorder.acc_x)} | "
                f"RR {len(self.recorder.rr_intervals)}"
            )

    def _toggle_recording(self) -> None:
        if self.record_btn.isChecked():
            name = self.session_input.text().strip() or default_session_name()
            self.session_input.setText(name)
            self.session_input.setEnabled(False)
            self.recorder.start(name)
            self.record_btn.setText("停止录制")
            self.rec_status.setText(f"录制中 → logs/{name}/")
            self.rec_status.setStyleSheet("color: #ef5350; font-weight: bold;")
        else:
            folder = self.recorder.stop()
            ecg_n = len(self.recorder.ecg_samples)
            acc_n = len(self.recorder.acc_x)
            rr_n = len(self.recorder.rr_intervals)
            self.record_btn.setText("开始录制")
            self.session_input.setEnabled(True)
            self.session_input.setText(default_session_name())
            self.rec_status.setText(f"已保存: {folder}")
            self.rec_status.setStyleSheet("color: #66bb6a;")
            QMessageBox.information(
                self,
                "录制完成",
                f"数据已保存至:\n{folder.resolve()}\n\n"
                f"  raw/  — 原始 npy/npz\n"
                f"  csv/  — CSV 导出\n\n"
                f"ECG: {ecg_n} 样本\n"
                f"ACC: {acc_n} 样本\n"
                f"RR: {rr_n} 个",
            )

    def closeEvent(self, event) -> None:
        if self.recorder.recording:
            reply = QMessageBox.question(
                self,
                "确认退出",
                "正在录制中，退出将自动保存当前数据。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.recorder.stop()

        self._refresh_timer.stop()
        self.worker.stop()
        super().closeEvent(event)


def run_app() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    app = QApplication([])
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    app.exec()
