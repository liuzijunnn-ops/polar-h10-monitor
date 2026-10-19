# Changelog

## 2026-10-19 — Public repository documentation and attribution

- Add a Chinese quick start, recording guide, troubleshooting, export schema and measurement limitations.
- Attribute polar-python / polar-display, preserve their MIT notices, and license the application under GPLv3 to match open-source PyQt6 usage.
- Exclude recording backups, IDE settings and build outputs from Git.
- Correct the NumPy requirement for `numpy.trapezoid` (requires NumPy 2.0+).
- Add synthetic protocol / HRV / export regression checks and include notices in packaged builds.
- Generalize the macOS pairing-error message instead of embedding one device identifier.

Historical v1.0.0 packages predate later BLE and session-handling fixes. Use the source or a build from the desired commit; package builds are not live hardware validation.
