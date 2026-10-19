"""Synthetic regression checks; no Bluetooth device or personal data required."""
import csv
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from hrv import compute_hrv, filter_valid_rr_intervals
from polar_ble import (
    PmdMeasurementType, PmdSettingType, TIMESTAMP_OFFSET_NS,
    encode_pmd_start, parse_acc_frame, parse_delta_frames_all,
    parse_ecg_frame, parse_hr_measurement, parse_pmd_frame,
)
from recorder import SessionRecorder


class ProtocolTests(unittest.TestCase):
    def test_hr_flags_and_rr_units(self):
        # 8-bit HR with two RR values in units of 1/1024 second.
        result = parse_hr_measurement(bytes([0x10, 60, 0, 4, 0, 2]))
        self.assertEqual(result.heartrate, 60)
        self.assertEqual(result.rr_intervals, [1000.0, 500.0])
        # uint16 HR + energy expenditure + RR.
        result = parse_hr_measurement(bytes([0x19, 44, 1, 99, 0, 0, 4]))
        self.assertEqual(result.heartrate, 300)
        self.assertEqual(result.rr_intervals, [1000.0])
        self.assertEqual(parse_hr_measurement(bytes([0, 70])).rr_intervals, [])

    def test_truncated_hr_is_rejected(self):
        for packet in (b"", b"\x00", b"\x01\x01"):
            with self.assertRaises(ValueError):
                parse_hr_measurement(packet)

    def test_ecg_signed_24_bit_and_packet_time(self):
        values = [-8388608, -1, 0, 8388607]
        packet = bytes([0]) + (123).to_bytes(8, "little") + bytes([0])
        packet += b"".join(value.to_bytes(3, "little", signed=True) for value in values)
        frame = parse_pmd_frame(packet, lambda _: None)
        data = parse_ecg_frame(frame)
        self.assertEqual(data.data, values)
        self.assertEqual(data.timestamp, TIMESTAMP_OFFSET_NS + 123)

    def test_acc_signed_16_bit(self):
        packet = bytes([2]) + (456).to_bytes(8, "little") + bytes([1])
        packet += b"".join(value.to_bytes(2, "little", signed=True) for value in (-1000, 0, 1000))
        data = parse_acc_frame(parse_pmd_frame(packet, lambda _: None))
        self.assertEqual(data.data, [(-1000, 0, 1000)])

    def test_delta_decode_signed_steps(self):
        # Reference 10; two signed 4-bit deltas +1 and -2 => 11, 9.
        self.assertEqual(parse_delta_frames_all(bytes([10, 0, 4, 2, 0xE1]), 1, 16, True), [[10], [11], [9]])

    def test_start_command_layout(self):
        self.assertEqual(
            encode_pmd_start(PmdMeasurementType.ECG, [(PmdSettingType.SAMPLE_RATE, [130]), (PmdSettingType.RESOLUTION, [14])]),
            bytes([2, 0, 0, 1, 130, 0, 1, 1, 14, 0]),
        )


class HRVTests(unittest.TestCase):
    def test_filter_and_independent_time_domain_values(self):
        self.assertEqual(filter_valid_rr_intervals([float("nan"), float("inf"), 299, 300, 2000, 2001]), [300, 2000])
        metrics = compute_hrv([800, 1000, 1200], include_frequency=False)
        self.assertEqual(metrics.count, 3)
        self.assertEqual(metrics.mean_rr_ms, 1000)
        self.assertEqual(metrics.mean_hr_bpm, 60)
        self.assertEqual(metrics.sdnn_ms, 200)
        self.assertEqual(metrics.rmssd_ms, 200)
        self.assertEqual(metrics.pnn50_pct, 100)
        self.assertIsNone(compute_hrv([800]))

    def test_frequency_duration_and_constant_signal(self):
        self.assertIsNone(compute_hrv([1000] * 59).frequency)
        metrics = compute_hrv([1000] * 90)
        self.assertIsNotNone(metrics.frequency)
        self.assertAlmostEqual(metrics.frequency.total_power_ms2, 0)

    def test_synthetic_hf_modulation_dominates_lf(self):
        rr = [1000 + 40 * math.sin(2 * math.pi * 0.25 * t) for t in range(240)]
        frequency = compute_hrv(rr).frequency
        self.assertTrue(np.isfinite(frequency.hf_power_ms2))
        self.assertGreater(frequency.hf_power_ms2, 10 * frequency.lf_power_ms2)


class ExportTests(unittest.TestCase):
    def test_roundtrip_and_session_reset(self):
        with tempfile.TemporaryDirectory() as folder, patch("recorder.LOGS_DIR", Path(folder)):
            recorder = SessionRecorder()
            recorder.start("synthetic_session")
            recorder.add_ecg(123, [-1, 2])
            recorder.add_acc(456, [(1, 2, 3)])
            recorder.add_hr(60, [1000] * 90)
            output = recorder.stop()
            self.assertEqual(np.load(output / "raw/ecg.npy", allow_pickle=False).tolist(), [-1, 2])
            self.assertEqual(np.load(output / "raw/ecg_timestamps.npy", allow_pickle=False).tolist(), [123, 123])
            with np.load(output / "raw/rr.npz", allow_pickle=False) as rr:
                self.assertEqual(len(rr["rr_intervals_ms"]), 90)
            with (output / "csv/acc.csv").open() as stream:
                rows = list(csv.reader(stream))
            self.assertEqual(rows[1], ["0", "456", "1", "2", "3"])
            meta = json.loads((output / "meta.json").read_text())
            self.assertEqual((meta["ecg_samples"], meta["acc_samples"], meta["rr_count"]), (2, 1, 90))
            self.assertIn("frequency", json.loads((output / "hrv.json").read_text()))
            recorder.start("second_session")
            self.assertEqual(recorder.ecg_samples, [])
            self.assertEqual(recorder.rr_intervals, [])
            second = recorder.stop()
            self.assertFalse((second / "raw/ecg.npy").exists())
            self.assertFalse((second / "hrv.json").exists())


if __name__ == "__main__":
    unittest.main()
