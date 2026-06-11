"""Background BLE worker for Polar H10 streaming."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from typing import Any

from bleak import BleakClient, BleakScanner
from PyQt6.QtCore import QObject, pyqtSignal

from polar_python import PolarDevice
from polar_python.constants import PolarCharacteristic
from polar_python.models import ACCData, ECGData, HRData

logger = logging.getLogger(__name__)

SCAN_TIMEOUT_SEC = 12.0
POLAR_NAME_FRAGMENT = "polar h10"
DEVICE_HINT_ENV = "POLAR_DEVICE"


def _device_names(device: Any, adv_data: Any | None = None) -> list[str]:
    names = [getattr(device, "name", None)]
    if adv_data is not None:
        names.append(getattr(adv_data, "local_name", None))
    return [name for name in names if isinstance(name, str) and name.strip()]


def _device_label(device: Any, adv_data: Any | None = None) -> str:
    names = _device_names(device, adv_data)
    name = names[0] if names else "未知设备"
    address = getattr(device, "address", "unknown-address")
    return f"{name} ({address})"


def _matches_hint(device: Any, adv_data: Any | None, hint: str) -> bool:
    haystack = [getattr(device, "address", "")]
    haystack.extend(_device_names(device, adv_data))
    return any(hint in item.lower() for item in haystack if item)


def _matches_polar_h10(device: Any, adv_data: Any | None = None) -> bool:
    return any(POLAR_NAME_FRAGMENT in name.lower() for name in _device_names(device, adv_data))


def _log_scan_results(results: list[tuple[Any, Any | None]]) -> None:
    lines: list[str] = []
    for device, adv_data in results:
        uuids = getattr(adv_data, "service_uuids", None) if adv_data is not None else None
        rssi = getattr(adv_data, "rssi", None) if adv_data is not None else None
        lines.append(
            f"{_device_label(device, adv_data)} | rssi={rssi} | service_uuids={uuids or []}"
        )
    logger.info("BLE scan discovered %d device(s): %s", len(results), "; ".join(lines))


def _prepare_windows_ble_thread() -> None:
    if sys.platform != "win32":
        return
    try:
        from bleak.backends.winrt.util import uninitialize_sta
    except ImportError:
        return
    try:
        uninitialize_sta()
    except Exception:
        logger.debug("Unable to uninitialize WinRT STA state", exc_info=True)


class PairingPolarDevice(PolarDevice):
    def __init__(self, address_or_ble_device: Any) -> None:
        super().__init__(address_or_ble_device)
        if sys.platform == "win32":
            self._client = BleakClient(address_or_ble_device, pair=True, timeout=30.0)

    async def connect(self) -> None:
        if sys.platform != "win32":
            await super().connect()
            return

        logger.info("Connecting with Windows pairing enabled")
        await self._client.connect()

        await self._client.start_notify(
            PolarCharacteristic.PMD_CONTROL_POINT.value,
            self._handle_pmd_control,
        )
        await self._client.start_notify(
            PolarCharacteristic.PMD_DATA.value,
            self._handle_pmd_data,
        )


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
        _prepare_windows_ble_thread()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        except Exception as exc:
            logger.exception("BLE worker failed")
            self.error.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self._loop.close()
            self.status_changed.emit("已断开")

    async def _scan_for_device(self) -> Any | None:
        hint = os.getenv(DEVICE_HINT_ENV, "").strip().lower()

        try:
            discovered = await BleakScanner.discover(timeout=SCAN_TIMEOUT_SEC, return_adv=True)
            results = [(device, adv_data) for device, adv_data in discovered.values()]
        except TypeError:
            devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT_SEC)
            results = [(device, None) for device in devices]

        _log_scan_results(results)

        if hint:
            hinted = [device for device, adv_data in results if _matches_hint(device, adv_data, hint)]
            if hinted:
                return hinted[0]

        polar_devices = [
            device for device, adv_data in results if _matches_polar_h10(device, adv_data)
        ]
        if polar_devices:
            return polar_devices[0]

        return None

    async def _main(self) -> None:
        self.status_changed.emit("正在扫描 Polar H10...")
        device = await self._scan_for_device()
        if device is None:
            self.error.emit(
                "未找到 Polar H10。请确认设备已开启、贴片已佩戴、没有被手机 App 占用；"
                f"Windows 可设置环境变量 {DEVICE_HINT_ENV}=设备名或地址片段后重试。"
            )
            return

        device_name = device.name or "Polar H10"
        self.status_changed.emit(f"正在连接 {device_name}...")
        logger.info("Connecting to BLE device: %s", _device_label(device))
        async with PairingPolarDevice(device) as polar_device:
            self.connected.emit(device_name)

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
