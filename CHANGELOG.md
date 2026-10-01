# Changelog

## 1.0.0 — 2026-10-01

First public release.

- Automatic detection of the port, speed, framing (8N1, 7E1, 7O1 …) and protocol, with quick and thorough modes,
  confidence score, raw samples and a cancel button. Read-only requests only.
- Protocol library: Mettler Toledo MT-SICS and Toledo Continuous, A&D, SMA, NCI 3835, Ohaus, Sartorius SBI,
  CAS (experimental), XK3190 (tF=0 and reversed stream), Mahak MDS (field-tested), generic text, custom binary and
  custom text formats.
- Saved scale profiles and a parsed-weight API: `GET/POST /weight` with value, unit, stability, net/gross,
  overload, age and checksum result; unit conversion.
- Compatible with SyncPulse Serial Bridge 1.x (`/health`, `/ports`, `POST /read`, `bridge.json`).
- Bilingual control page (English/Persian): live weights, auto-detection, connection details, access key,
  allowed clients, raw monitor with protocol guesses, protocol library, about.
- One-click Windows Firewall rule and start-with-Windows task (SYSTEM, no 72-hour limit, restart on failure),
  both with a UAC prompt.
- Single-file Windows program with version information; single-instance start that opens the running copy.
- Simulated scales for every protocol (`--simulate`) and a test suite that needs no hardware.
