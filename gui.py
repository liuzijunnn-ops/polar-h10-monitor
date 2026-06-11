"""PyQt6 GUI for real-time Polar H10 monitoring and recording."""

from __future__ import annotations

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime
import logging
import time

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
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
from hrv import MIN_DURATION_LIVE, compute_freq_hrv, compute_hrv, rr_cumulative_duration_sec
from paths import LOGS_DIR
from polar_python.models import ACCData, ECGData, HRData
from recorder import ACC_SAMPLE_RATE, ECG_SAMPLE_RATE, SessionRecorder, default_session_name

logger = logging.getLogger(__name__)

RR_WINDOW = 60  # time-domain rolling window (beats)
RR_FREQ_WINDOW = 150  # frequency needs ~45–60 s cumulative RR; 60 beats alone is often <60 s
PLOT_REFRESH_MS = 16  # ~60 fps display refresh
FREQ_UPDATE_MIN_INTERVAL_SEC = 5.0
ECG_SAMPLE_RATE_HZ = ECG_SAMPLE_RATE
ACC_SAMPLE_RATE_HZ = ACC_SAMPLE_RATE


class MainWindow(QMainWindow):
    freq_hrv_ready = pyqtSignal(object, float, int)
    freq_hrv_failed = pyqtSignal(str)

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
        self._rr_freq_window: deque[float] = deque(maxlen=RR_FREQ_WINDOW)

        self._ecg_dirty = False
        self._acc_dirty = False

        self._hrv_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hrv")
        self._freq_future: Future | None = None
        self._last_freq_started_at = 0.0
        self._freq_generation = 0

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

        freq_box = QGroupBox(f"HRV 频域 (需 ≥{int(MIN_DURATION_LIVE)}s RR)")
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
        self.freq_status = QLabel("累积 RR 时长: 0s")
        self.freq_status.setStyleSheet("color: #888; font-size: 11px;")
        self.freq_status.setWordWrap(True)
        freq_layout.addWidget(self.freq_status, len(freq_metrics), 0, 1, 2)
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
            vb.enableAutoRange(x=False, y=False)

        self.ecg_plot.setXRange(0, 1, padding=0.02)
        self.acc_plot.setXRange(0, 1, padding=0.02)

        self.ecg_curve = self.ecg_plot.plot(pen=pg.mkPen("#00e676", width=1))
        self.ecg_curve.setClipToView(True)
        self.ecg_curve.setDownsampling(auto=True, method="peak")

        self.acc_x_curve = self.acc_plot.plot(pen=pg.mkPen("#ff9e80", width=1), name="X")
        self.acc_y_curve = self.acc_plot.plot(pen=pg.mkPen("#80d8ff", width=1), name="Y")
        self.acc_z_curve = self.acc_plot.plot(pen=pg.mkPen("#b388ff", width=1), name="Z")
        for curve in (self.acc_x_curve, self.acc_y_curve, self.acc_z_curve):
            curve.setClipToView(True)
            curve.setDownsampling(auto=True, method="peak")

    def _connect_signals(self) -> None:
        self.worker.ecg_received.connect(self._on_ecg)
        self.worker.acc_received.connect(self._on_acc)
        self.worker.hr_received.connect(self._on_hr)
        self.worker.status_changed.connect(self._on_status)
        self.worker.connected.connect(self._on_connected)
        self.worker.error.connect(self._on_error)
        self.freq_hrv_ready.connect(self._on_freq_hrv_ready)
        self.freq_hrv_failed.connect(self._on_freq_hrv_failed)

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
                self._rr_freq_window.append(rr)
            self._update_hrv_display()
        self.recorder.add_hr(data.heartrate, data.rr_intervals)

    def _reset_live_hrv_display(self) -> None:
        self._rr_window.clear()
        self._rr_freq_window.clear()
        self._freq_generation += 1
        if self._freq_future is not None and not self._freq_future.done():
            self._freq_future.cancel()
        self._freq_future = None
        self._last_freq_started_at = 0.0

        self.hr_value.setText("--")
        self.rr_value.setText("--")
        for label in self.hrv_labels.values():
            label.setText("--")
        self._clear_freq_display(0.0, 0)

    def _update_hrv_display(self) -> None:
        rr_time = list(self._rr_window)
        rr_freq = list(self._rr_freq_window)
        freq_duration = rr_cumulative_duration_sec(rr_freq)

        metrics = compute_hrv(rr_time, include_frequency=False)
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

        self._schedule_freq_hrv(rr_freq, freq_duration)

    def _clear_freq_display(self, freq_duration: float, rr_count: int) -> None:
        for label in self.freq_labels.values():
            label.setText("--")
        need = max(0.0, MIN_DURATION_LIVE - freq_duration)
        self.freq_status.setText(
            f"累积 RR 时长: {freq_duration:.0f}s / {int(MIN_DURATION_LIVE)}s"
            f"（还需约 {need:.0f}s）| 窗口 {rr_count} 拍"
        )
        self.freq_status.setStyleSheet("color: #888; font-size: 11px;")

    def _schedule_freq_hrv(self, rr_freq: list[float], freq_duration: float) -> None:
        rr_count = len(rr_freq)
        if freq_duration < MIN_DURATION_LIVE:
            self._clear_freq_display(freq_duration, rr_count)
            return

        if self._freq_future is not None and not self._freq_future.done():
            self.freq_status.setText(
                f"累积 RR 时长: {freq_duration:.0f}s | 窗口 {rr_count} 拍 | 频域计算中..."
            )
            self.freq_status.setStyleSheet("color: #888; font-size: 11px;")
            return

        now = time.monotonic()
        if now - self._last_freq_started_at < FREQ_UPDATE_MIN_INTERVAL_SEC:
            return

        snapshot = list(rr_freq)
        generation = self._freq_generation
        self._last_freq_started_at = now
        self.freq_status.setText(
            f"累积 RR 时长: {freq_duration:.0f}s | 窗口 {rr_count} 拍 | 频域计算中..."
        )
        self.freq_status.setStyleSheet("color: #888; font-size: 11px;")
        self._freq_future = self._hrv_executor.submit(
            compute_freq_hrv,
            snapshot,
            min_duration_sec=MIN_DURATION_LIVE,
        )
        self._freq_future.add_done_callback(
            lambda future: self._emit_freq_result(future, freq_duration, rr_count, generation)
        )

    def _emit_freq_result(
        self, future: Future, freq_duration: float, rr_count: int, generation: int
    ) -> None:
        if future.cancelled() or generation != self._freq_generation:
            return
        try:
            metrics = future.result()
        except Exception as exc:
            logger.exception("Frequency-domain HRV calculation failed")
            self.freq_hrv_failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.freq_hrv_ready.emit(metrics, freq_duration, rr_count)

    def _on_freq_hrv_ready(self, metrics: object, freq_duration: float, rr_count: int) -> None:
        if metrics is None:
            self._clear_freq_display(freq_duration, rr_count)
            return

        for key, label in self.freq_labels.items():
            value = getattr(metrics, key)
            label.setText(f"{value:.2f}")
        self.freq_status.setText(f"累积 RR 时长: {freq_duration:.0f}s | 窗口 {rr_count} 拍")
        self.freq_status.setStyleSheet("color: #66bb6a; font-size: 11px;")

    def _on_freq_hrv_failed(self, text: str) -> None:
        for label in self.freq_labels.values():
            label.setText("--")
        self.freq_status.setText(f"频域计算失败: {text}")
        self.freq_status.setStyleSheet("color: #ef5350; font-size: 11px;")

    def _is_viewing_all(self, plot: pg.PlotWidget, total: int, margin: float = 0.02) -> bool:
        """True if x-axis shows the full buffer (user hasn't zoomed/panned to a sub-range)."""
        if total <= 1:
            return True
        x0, x1 = plot.getViewBox().viewRange()[0]
        span = x1 - x0
        full_span = max(total, 1)
        return x0 <= full_span * margin and x1 >= full_span * (1.0 - margin) and span >= full_span * (
            1.0 - 2 * margin
        )

    def _apply_view_all_x(self, plot: pg.PlotWidget, total: int) -> None:
        if total <= 0:
            plot.setXRange(0, 1, padding=0.02)
        else:
            plot.setXRange(0, total, padding=0.02)

    def _refresh_plots(self) -> None:
        if self._ecg_dirty and self._ecg_buffer:
            n = len(self._ecg_buffer)
            xs = np.arange(n, dtype=np.float64)
            self.ecg_curve.setData(xs, np.asarray(self._ecg_buffer, dtype=np.float32))
            if self._is_viewing_all(self.ecg_plot, n):
                self._apply_view_all_x(self.ecg_plot, n)
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
            if self._is_viewing_all(self.acc_plot, n):
                self._apply_view_all_x(self.acc_plot, n)
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
            self._reset_live_hrv_display()
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
            self._reset_live_hrv_display()
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
        if self._freq_future is not None and not self._freq_future.done():
            self._freq_future.cancel()
        self._hrv_executor.shutdown(wait=False, cancel_futures=True)
        super().closeEvent(event)


def run_app() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOGS_DIR / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logger.info("Starting Polar H10 monitor")
    app = QApplication([])
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    app.exec()
