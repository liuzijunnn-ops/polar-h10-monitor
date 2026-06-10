"""Background BLE worker for Polar H10 streaming."""

from __future__ import annotations

import asyncio
import threading

from bleak import BleakScanner
from PyQt6.QtCore import QObject, pyqtSignal

from polar_python import PolarDevice
from polar_python.models import ACCData, ECGData, HRData


class PolarWorker(QObject):
    ecg_received = pyqtSignal(object)
    acc_received = pyqtSignal(object)
    hr_received = pyqtSignal(object)
    status_changed = pyqtSignal(str)
    connected = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: None)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._loop.close()
            self.status_changed.emit("已断开")

    async def _main(self) -> None:
        self.status_changed.emit("正在扫描 Polar H10...")
        device = await BleakScanner.find_device_by_filter(
            lambda bd, _ad: bd.name is not None and "Polar H10" in bd.name,
            timeout=10,
        )
        if device is None:
            self.error.emit("未找到 Polar H10，请确认设备已开启并在附近。")
            return

        self.status_changed.emit(f"正在连接 {device.name}...")
        async with PolarDevice(device) as polar_device:
            self.connected.emit(device.name or "Polar H10")

            def ecg_callback(data: ECGData) -> None:
                self.ecg_received.emit(data)

            def acc_callback(data: ACCData) -> None:
                self.acc_received.emit(data)

            def hr_callback(data: HRData) -> None:
                self.hr_received.emit(data)

            await polar_device.start_ecg_stream(
                ecg_callback=ecg_callback, sample_rate=130, resolution=14
            )
            await polar_device.start_acc_stream(
                acc_callback=acc_callback, sample_rate=25, resolution=16, range=2
            )
            await polar_device.start_hr_stream(hr_callback=hr_callback)

            self.status_changed.emit("数据流已启动")

            while not self._stop_event.is_set():
                await asyncio.sleep(0.1)
