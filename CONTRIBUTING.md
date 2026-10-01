# Contributing

Thank you for helping more scales work out of the box.

## Reporting a scale that is not recognised

Open an issue with:

- the brand and model of the indicator, and its serial settings menu if you know it;
- what **Manual & monitor** shows (hex and text) at the speed and framing that gives readable data;
- what the display showed at that moment (e.g. `0.550 kg`, stable).

## Adding a protocol

1. In `scale_bridge/protocols.py`, write a `Protocol` subclass whose `readings(data)` returns `Reading`s from raw
   bytes — value, unit, and `stable`/`net`/`overload`/`checksum_ok` when the format carries them. Never raise on
   bad input; skip what does not match.
2. Add it to `_catalogue()` with `kind`, the **read-only** `request` (if any), `families`, `reference` and
   `specificity` (3 = strictly framed or checksummed, 2 = distinctive text, 1 = loose).
3. Add its id to `CONTINUOUS_IDS` and/or `POLL_IDS` so detection tries it.
4. Teach `scale_bridge/simulator.py` to produce it (`frame_for`, and `REQUESTS` or `CONTINUOUS`).
5. Add tests in `tests/test_protocols.py` with sample frames from the manufacturer's document, and a case in
   `tests/test_detect.py`.
6. Run `python -m pytest`.

Never add a request that changes the scale (zero, tare, reset, print, display off, configuration) to detection.

## Code

- Python 3.9+, standard library plus `pyserial` only.
- Keep the source headers (SPDX line and copyright) and the author attribution described in [NOTICE.md](NOTICE.md).
- Contributions are accepted under the project's licence (GPL-3.0-or-later with the section 7(b) attribution term).
