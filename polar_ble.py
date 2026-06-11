"""Native Polar H10 BLE protocol client.

This module intentionally keeps the Windows data path independent from
polar-python. It uses Bleak directly for the standard Heart Rate service and
Polar PMD ECG/ACC streams.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum
import logging
import math
import struct
import sys
from typing import Any

from bleak import BleakClient

logger = logging.getLogger(__name__)

TIMESTAMP_OFFSET_NS = 946684800000000000

HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"
PMD_SERVICE_UUID = "fb005c80-02e7-f387-1cad-8acd2d8df0c8"
PMD_CONTROL_POINT_UUID = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA_UUID = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"


class PmdMeasurementType(IntEnum):
    ECG = 0
    PPG = 1
    ACC = 2
    PPI = 3
    RFU = 4
    GYRO = 5
    MAG = 6


class PmdControlOperation(IntEnum):
    GET = 0x01
    START = 0x02
    STOP = 0x03


class PmdSettingType(IntEnum):
    SAMPLE_RATE = 0
    RESOLUTION = 1
    RANGE = 2
    RANGE_MILLIUNIT = 3
    CHANNELS = 4
    FACTOR = 5
    SECURITY = 6
    UNKNOWN = 255

    @property
    def field_size(self) -> int:
        if self in {PmdSettingType.RANGE_MILLIUNIT, PmdSettingType.FACTOR}:
            return 4
        if self == PmdSettingType.CHANNELS:
            return 1
        if self == PmdSettingType.SECURITY:
            return 16
        return 2


class PmdControlError(IntEnum):
    SUCCESS = 0
    ERROR_INVALID_OP_CODE = 1
    ERROR_INVALID_MEASUREMENT_TYPE = 2
    ERROR_NOT_SUPPORTED = 3
    ERROR_INVALID_LENGTH = 4
    ERROR_INVALID_PARAMETER = 5
    ERROR_ALREADY_IN_STATE = 6
    ERROR_INVALID_RESOLUTION = 7
    ERROR_INVALID_SAMPLE_RATE = 8
    ERROR_INVALID_RANGE = 9
    ERROR_INVALID_MTU = 10
    ERROR_INVALID_NUMBER_OF_CHANNELS = 11
    ERROR_INVALID_STATE = 12
    ERROR_DEVICE_IN_CHARGER = 13


@dataclass
class HRData:
    heartrate: int
    rr_intervals: list[float]


@dataclass
class ECGData:
    timestamp: int
    data: list[int]


@dataclass
class ACCData:
    timestamp: int
    data: list[tuple[int, int, int]]


@dataclass
class PmdControlResponse:
    measurement_type: PmdMeasurementType
    error_code: PmdControlError
    more_frames: bool
    settings: list[tuple[PmdSettingType, list[int]]]


@dataclass
class PmdFrame:
    measurement_type: PmdMeasurementType
    timestamp: int
    frame_type: int
    compressed: bool
    content: bytes
    factor: float


def _setting_type(value: int) -> PmdSettingType:
    try:
        return PmdSettingType(value)
    except ValueError:
        return PmdSettingType.UNKNOWN


def encode_pmd_start(
    measurement_type: PmdMeasurementType,
    settings: Sequence[tuple[PmdSettingType, Sequence[int]]],
) -> bytes:
    data = bytearray([PmdControlOperation.START, measurement_type])
    for setting_type, values in settings:
        data.extend([setting_type, len(values)])
        field_size = setting_type.field_size
        for value in values:
            data.extend(int(value).to_bytes(field_size, "little", signed=False))
    return bytes(data)


def encode_pmd_stop(measurement_type: PmdMeasurementType) -> bytes:
    return bytes([PmdControlOperation.STOP, measurement_type])


def parse_pmd_control_response(data: bytes | bytearray | memoryview) -> PmdControlResponse:
    payload = bytes(data)
    if len(payload) < 5 or payload[0] != 0xF0:
        raise ValueError(f"Unexpected PMD control response: {payload.hex()}")

    measurement_type = PmdMeasurementType(payload[2])
    error_code = PmdControlError(payload[3])
    more_frames = payload[4] != 0
    settings: list[tuple[PmdSettingType, list[int]]] = []

    index = 5
    while index + 2 <= len(payload):
        setting_type = _setting_type(payload[index])
        if setting_type == PmdSettingType.UNKNOWN:
            break
        array_length = payload[index + 1]
        field_size = setting_type.field_size
        values_start = index + 2
        values_end = values_start + field_size * array_length
        if values_end > len(payload):
            break

        values = [
            int.from_bytes(payload[pos : pos + field_size], "little", signed=False)
            for pos in range(values_start, values_end, field_size)
        ]
        settings.append((setting_type, values))
        index = values_end

    return PmdControlResponse(
        measurement_type=measurement_type,
        error_code=error_code,
        more_frames=more_frames,
        settings=settings,
    )


def parse_hr_measurement(data: bytes | bytearray | memoryview) -> HRData:
    payload = bytes(data)
    if len(payload) < 2:
        raise ValueError("Heart Rate Measurement payload is too short")

    flags = payload[0]
    offset = 1
    if flags & 0x01:
        if len(payload) < offset + 2:
            raise ValueError("Heart Rate Measurement payload misses uint16 heart rate")
        heartrate = int.from_bytes(payload[offset : offset + 2], "little")
        offset += 2
    else:
        heartrate = payload[offset]
        offset += 1

    if flags & 0x08:
        offset += 2

    rr_intervals: list[float] = []
    if flags & 0x10:
        while offset + 2 <= len(payload):
            rr_raw = int.from_bytes(payload[offset : offset + 2], "little")
            rr_intervals.append(rr_raw * 1000.0 / 1024.0)
            offset += 2

    return HRData(heartrate=heartrate, rr_intervals=rr_intervals)


def parse_delta_frames_all(
    data: Sequence[int],
    channels: int,
    resolution: int,
    signed: bool,
) -> list[list[int]]:
    if not data:
        return []

    offset = 0
    ref_samples = _parse_delta_ref_samples(data, channels, resolution, signed)
    offset += int(channels * math.ceil(resolution / 8.0))
    samples = [ref_samples]

    while offset + 2 <= len(data):
        delta_size = data[offset] & 0xFF
        sample_count = data[offset + 1] & 0xFF
        offset += 2

        bit_length = sample_count * delta_size * channels
        byte_length = int(math.ceil(bit_length / 8.0))
        if offset + byte_length > len(data):
            break

        delta_samples = _parse_delta_frame(
            data[offset : offset + byte_length],
            channels=channels,
            bit_width=delta_size,
            total_bit_length=bit_length,
        )
        for delta in delta_samples:
            if len(delta) != channels:
                continue
            last_sample = samples[-1]
            samples.append([last_sample[i] + delta[i] for i in range(channels)])

        offset += byte_length

    return samples


def _parse_delta_ref_samples(
    data: Sequence[int],
    channels: int,
    resolution: int,
    signed: bool,
) -> list[int]:
    samples: list[int] = []
    offset = 0
    width = int(math.ceil(resolution / 8.0))
    for _ in range(channels):
        if offset + width > len(data):
            break
        samples.append(int.from_bytes(data[offset : offset + width], "little", signed=signed))
        offset += width
    return samples


def _parse_delta_frame(
    data: Sequence[int],
    channels: int,
    bit_width: int,
    total_bit_length: int,
) -> list[list[int]]:
    if not data or bit_width <= 0 or channels <= 0:
        return []

    bits: list[int] = []
    for byte_value in data:
        for bit_index in range(8):
            bits.append((byte_value >> bit_index) & 1)

    samples: list[list[int]] = []
    offset = 0
    while offset < total_bit_length and offset + bit_width * channels <= len(bits):
        channel_values: list[int] = []
        for _ in range(channels):
            value = 0
            for bit_index in range(bit_width):
                value |= bits[offset + bit_index] << bit_index
            if bit_width > 1 and (value & (1 << (bit_width - 1))):
                value |= -1 << bit_width
            channel_values.append(value)
            offset += bit_width
        samples.append(channel_values)

    return samples


def parse_pmd_frame(
    data: bytes | bytearray | memoryview,
    get_factor: Callable[[PmdMeasurementType], float | None],
) -> PmdFrame:
    payload = bytes(data)
    if len(payload) < 10:
        raise ValueError("PMD data frame is too short")

    measurement_type = PmdMeasurementType(payload[0])
    timestamp = int.from_bytes(payload[1:9], "little") + TIMESTAMP_OFFSET_NS
    frame_type_byte = payload[9]
    frame_type = frame_type_byte & 0x7F
    compressed = (frame_type_byte & 0x80) != 0
    factor = get_factor(measurement_type) or 1.0

    return PmdFrame(
        measurement_type=measurement_type,
        timestamp=timestamp,
        frame_type=frame_type,
        compressed=compressed,
        content=payload[10:],
        factor=factor,
    )


def parse_ecg_frame(frame: PmdFrame) -> ECGData:
    if frame.compressed or frame.frame_type != 0:
        raise ValueError(f"Unsupported ECG frame type: compressed={frame.compressed} type={frame.frame_type}")

    samples = [
        int.from_bytes(frame.content[index : index + 3], "little", signed=True)
        for index in range(0, len(frame.content) - 2, 3)
    ]
    return ECGData(timestamp=frame.timestamp, data=samples)


def parse_acc_frame(frame: PmdFrame) -> ACCData:
    if frame.compressed:
        if frame.frame_type == 0:
            raw_samples = parse_delta_frames_all(
                frame.content,
                channels=3,
                resolution=16,
                signed=True,
            )
            factor = frame.factor * 1000.0
        elif frame.frame_type == 1:
            raw_samples = parse_delta_frames_all(
                frame.content,
                channels=3,
                resolution=16,
                signed=True,
            )
            factor = frame.factor
        else:
            raise ValueError(f"Unsupported compressed ACC frame type: {frame.frame_type}")

        samples = [
            (int(sample[0] * factor), int(sample[1] * factor), int(sample[2] * factor))
            for sample in raw_samples
            if len(sample) == 3
        ]
        return ACCData(timestamp=frame.timestamp, data=samples)

    if frame.frame_type == 0:
        step = 1
    elif frame.frame_type == 1:
        step = 2
    else:
        raise ValueError(f"Unsupported raw ACC frame type: {frame.frame_type}")

    samples: list[tuple[int, int, int]] = []
    offset = 0
    while offset + step * 3 <= len(frame.content):
        x = int.from_bytes(frame.content[offset : offset + step], "little", signed=True)
        offset += step
        y = int.from_bytes(frame.content[offset : offset + step], "little", signed=True)
        offset += step
        z = int.from_bytes(frame.content[offset : offset + step], "little", signed=True)
        offset += step
        samples.append((x, y, z))

    return ACCData(timestamp=frame.timestamp, data=samples)


def _is_windows_auth_error(exc: BaseException) -> bool:
    text = f"{type(exc).__name__}: {exc}".lower()
    return (
        "insufficient authentication" in text
        or "access is denied" in text
        or "protocol error" in text
        or "-2147023673" in text
        or "operation was canceled" in text
        or "操作已被用户取消" in text
    )


class RawPolarClient:
    def __init__(
        self,
        device: Any,
        *,
        enable_pmd: bool,
        allow_pairing_retry: bool = True,
    ) -> None:
        self._device = device
        self._enable_pmd = enable_pmd
        self._allow_pairing_retry = allow_pairing_retry
        self._client: BleakClient | None = None
        self._pmd_control_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._factors: dict[PmdMeasurementType, float] = {}
        self._ecg_callback: Callable[[ECGData], None] | None = None
        self._acc_callback: Callable[[ACCData], None] | None = None
        self._hr_callback: Callable[[HRData], None] | None = None
        self._hr_packet_count = 0

    async def __aenter__(self) -> "RawPolarClient":
        await self.connect()
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        await self._connect_once()
        if not self._enable_pmd:
            return

        try:
            await self._start_pmd_notifications()
        except Exception as exc:
            if sys.platform != "win32" or not self._allow_pairing_retry or not _is_windows_auth_error(exc):
                raise

            logger.warning("PMD notify failed before pairing retry: %s", exc)
            await self._pair_disconnect_and_reconnect()
            await self._start_pmd_notifications()

    async def disconnect(self) -> None:
        if self._client is None:
            return
        try:
            if self._client.is_connected:
                await self._client.disconnect()
        finally:
            self._client = None

    async def start_ecg_stream(self, callback: Callable[[ECGData], None]) -> None:
        self._ecg_callback = callback
        await self._start_stream(
            PmdMeasurementType.ECG,
            [
                (PmdSettingType.SAMPLE_RATE, [130]),
                (PmdSettingType.RESOLUTION, [14]),
            ],
        )

    async def start_acc_stream(self, callback: Callable[[ACCData], None]) -> None:
        self._acc_callback = callback
        await self._start_stream(
            PmdMeasurementType.ACC,
            [
                (PmdSettingType.SAMPLE_RATE, [25]),
                (PmdSettingType.RESOLUTION, [16]),
                (PmdSettingType.RANGE, [2]),
            ],
        )

    async def start_hr_stream(self, callback: Callable[[HRData], None]) -> None:
        self._hr_callback = callback
        client = self._require_client()
        await client.start_notify(HEART_RATE_MEASUREMENT_UUID, self._handle_hr_measurement)
        logger.info("Started standard Heart Rate Measurement notifications")

    async def _connect_once(self) -> None:
        kwargs: dict[str, Any] = {"timeout": 30.0}
        services = [HEART_RATE_SERVICE_UUID]
        if self._enable_pmd:
            services.append(PMD_SERVICE_UUID)
        kwargs["services"] = services
        if sys.platform == "win32":
            kwargs["winrt"] = {"use_cached_services": False}

        self._client = BleakClient(self._device, **kwargs)
        await self._client.connect()
        self._log_services()

    async def _pair_disconnect_and_reconnect(self) -> None:
        client = self._require_client()
        paired = False
        for protection_level in (None, 2):
            try:
                logger.info("Attempting Windows BLE pair for Polar PMD, protection=%s", protection_level)
                paired = await asyncio.wait_for(
                    client.pair(protection_level=protection_level),
                    timeout=45.0,
                )
                logger.info("Windows BLE pair result for Polar PMD: %s", paired)
                break
            except TimeoutError:
                logger.warning("Windows BLE pair timed out, protection=%s", protection_level)
            except Exception as exc:
                logger.warning(
                    "Windows BLE pair failed, protection=%s: %s",
                    protection_level,
                    exc,
                )

        await self.disconnect()
        await asyncio.sleep(2.0)
        await self._connect_once()
        if not paired:
            logger.warning("Retrying Polar PMD without confirmed Windows pairing")

    async def _start_pmd_notifications(self) -> None:
        client = self._require_client()
        await client.start_notify(PMD_CONTROL_POINT_UUID, self._handle_pmd_control)
        logger.info("Started Polar PMD control notifications")
        await client.start_notify(PMD_DATA_UUID, self._handle_pmd_data)
        logger.info("Started Polar PMD data notifications")

    async def _start_stream(
        self,
        measurement_type: PmdMeasurementType,
        settings: Sequence[tuple[PmdSettingType, Sequence[int]]],
    ) -> None:
        client = self._require_client()
        request = encode_pmd_start(measurement_type, settings)
        logger.info("Starting PMD %s stream with request=%s", measurement_type.name, request.hex())
        await client.write_gatt_char(PMD_CONTROL_POINT_UUID, request, response=True)
        response = await asyncio.wait_for(self._pmd_control_queue.get(), timeout=10.0)
        parsed = parse_pmd_control_response(response)
        if parsed.measurement_type != measurement_type:
            raise RuntimeError(
                f"Unexpected PMD response type {parsed.measurement_type.name}; expected {measurement_type.name}"
            )
        if parsed.error_code != PmdControlError.SUCCESS:
            raise RuntimeError(f"PMD {measurement_type.name} start failed: {parsed.error_code.name}")

        for setting_type, values in parsed.settings:
            if setting_type == PmdSettingType.FACTOR and values:
                self._factors[measurement_type] = struct.unpack("<f", struct.pack("<I", values[0]))[0]
                logger.info(
                    "PMD %s factor=%s",
                    measurement_type.name,
                    self._factors[measurement_type],
                )
                break

        logger.info("Started PMD %s stream", measurement_type.name)

    def _handle_pmd_control(self, _sender: Any, data: bytearray) -> None:
        payload = bytes(data)
        logger.debug("PMD control packet: %s", payload.hex())
        if payload and payload[0] == 0xF0:
            self._pmd_control_queue.put_nowait(payload)

    def _handle_pmd_data(self, _sender: Any, data: bytearray) -> None:
        try:
            frame = parse_pmd_frame(data, self._factors.get)
            if frame.measurement_type == PmdMeasurementType.ECG and self._ecg_callback:
                parsed = parse_ecg_frame(frame)
                logger.debug("ECG packet: %d samples", len(parsed.data))
                self._ecg_callback(parsed)
            elif frame.measurement_type == PmdMeasurementType.ACC and self._acc_callback:
                parsed = parse_acc_frame(frame)
                logger.debug("ACC packet: %d samples", len(parsed.data))
                self._acc_callback(parsed)
        except Exception:
            logger.exception("Failed to parse Polar PMD data packet")

    def _handle_hr_measurement(self, _sender: Any, data: bytearray) -> None:
        try:
            parsed = parse_hr_measurement(data)
        except Exception:
            logger.exception("Failed to parse Heart Rate Measurement packet: %s", bytes(data).hex())
            return

        self._hr_packet_count += 1
        if self._hr_packet_count <= 5 or not parsed.rr_intervals:
            flags = data[0] if data else None
            logger.info(
                "HR packet #%d: flags=%s len=%d bpm=%d rr_count=%d raw=%s",
                self._hr_packet_count,
                f"0x{flags:02x}" if flags is not None else "none",
                len(data),
                parsed.heartrate,
                len(parsed.rr_intervals),
                bytes(data).hex(),
            )

        if self._hr_callback:
            self._hr_callback(parsed)

    def _log_services(self) -> None:
        client = self._require_client()
        try:
            services = client.services
        except Exception:
            logger.exception("Unable to inspect BLE services")
            return

        lines: list[str] = []
        for service in services:
            service_uuid = getattr(service, "uuid", "unknown-service")
            for char in getattr(service, "characteristics", []):
                lines.append(
                    f"{service_uuid} -> {getattr(char, 'uuid', 'unknown-char')}"
                    f" props={getattr(char, 'properties', [])}"
                )
        logger.info("Connected BLE services: %s", "; ".join(lines))

    def _require_client(self) -> BleakClient:
        if self._client is None:
            raise RuntimeError("Polar BLE client is not connected")
        return self._client
