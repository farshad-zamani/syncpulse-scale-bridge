# Changelog

## 1.1.0 — 2026-10-11

Scales that send only when their Print key is pressed — typically indicators wired to a label printer.

- New protocol `label_print`: reads the label an indicator sends to its label printer — TSPL/TSPL2 (TSC and
  compatibles), EPL2 (Zebra/Eltron, Argox) and ZPL (Zebra). The weight is the number printed with a weight unit;
  the other values on the label (order number, shift, date, time, thickness …) come along as `fields`.
  Field-tested on a PTC400 indicator printing to a TSC printer (TSPL, 9600 8N1).
- Auto-detection: new *wait for Print* option (`--wait-print SECONDS`) holds the port open until the operator
  presses Print, steps to the next speed if the data is unreadable, and reads 7E1/7O1 from a single press; new
  *listen only* option (`--listen-only`) never sends a byte to the device.
- The bridge keeps the ports of such scales open all the time and records every printed label: the last 500 in
  memory (`GET /labels?profile=…&after=SEQ`) and a daily `labels/<profile>-YYYY-MM-DD.jsonl` file.
- `/weight` answers include `fields` and `on_print`; a print-only scale answers at once ("waiting for the Print
  key") instead of holding the caller.
- The control page shows the last printed label, its fields and a short label history.

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
