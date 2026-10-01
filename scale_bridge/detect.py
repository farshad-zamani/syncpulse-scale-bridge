# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Auto-detection: find how the scale on a COM port talks.

1. LISTEN — at each common speed, in 8N1, for a moment. A scale that sends
   by itself shows up here. Readable text means the right speed; bytes that
   only become readable with their top bit cleared mean 7 data bits with
   parity (7E1/7O1), and the port is listened to again that way. Whatever
   arrives is matched against every continuous format in the library.

2. ASK — if nothing useful was heard, each read-only request in the library
   is sent at each speed and framing, and the reply is matched against the
   protocol that was asked. A reply is confirmed by asking a second time.

Everything is reported step by step through `log(code, **details)`, so the
user interface can show (and translate) what is happening.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .protocols import CONTINUOUS_IDS, POLL_IDS, PROTOCOLS, Reading
from .serialio import LineSettings, Opener, format_hex, printable

PASSIVE_BAUDS = [9600, 2400, 4800, 19200, 1200, 38400, 57600, 115200]
ACTIVE_QUICK = [(9600, "8N1"), (9600, "7E1"), (2400, "7E1"), (2400, "8N1"), (4800, "8N1"),
                (19200, "8N1"), (1200, "7E1"), (115200, "8N1")]
ACTIVE_THOROUGH = [(9600, "8N1"), (9600, "7E1"), (9600, "7O1"), (2400, "8N1"), (2400, "7E1"),
                   (4800, "8N1"), (4800, "7E1"), (19200, "8N1"), (19200, "7E1"), (1200, "8N1"),
                   (1200, "7E1"), (38400, "8N1"), (57600, "8N1"), (115200, "8N1")]
FRAMING_CHARS = {0x02, 0x03, 0x06, 0x0A, 0x0D, 0x09, 0x01, 0x04}


@dataclass
class Timings:
    passive_s: float = 1.3
    probe_s: float = 0.45
    confirm_s: float = 1.2
    drain_s: float = 0.06


def readability(data: bytes, mask7: bool = False) -> float:
    if not data:
        return 0.0
    ok = 0
    for b in data:
        if mask7:
            b &= 0x7F
        if 0x20 <= b <= 0x7E or b in FRAMING_CHARS:
            ok += 1
    return ok / len(data)


def _confidence(protocol_id: str, readings: list[Reading]) -> float:
    spec = PROTOCOLS[protocol_id].specificity
    base = {3: 0.9, 2: 0.8, 1: 0.6}.get(spec, 0.5)
    if any(r.checksum_ok for r in readings):
        base += 0.08
    if len(readings) >= 3:
        base += 0.02
    return round(min(base, 0.99), 2)


class Detector:
    def __init__(self, opener: Opener, log: Callable[..., None] = lambda code, **kw: None,
                 cancelled: Callable[[], bool] = lambda: False, thorough: bool = False,
                 timings: Optional[Timings] = None):
        self.opener = opener
        self.log = log
        self.cancelled = cancelled
        self.thorough = thorough
        self.t = timings or Timings()
        self.active_combos = ACTIVE_THOROUGH if thorough else ACTIVE_QUICK
        self.steps_done = 0

    # -- plumbing ----------------------------------------------------------
    def _step(self) -> None:
        self.steps_done += 1

    @property
    def steps_per_port(self) -> int:
        return len(PASSIVE_BAUDS) + len(self.active_combos) * len(POLL_IDS)

    @property
    def progress(self) -> float:
        """How far the port being searched is, 0..1."""
        return min(1.0, self.steps_done / self.steps_per_port)

    def _drain(self, ser: Any, seconds: float) -> bytes:
        buf = bytearray()
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            waiting = ser.in_waiting
            buf += ser.read(waiting if waiting else 1)
        return bytes(buf)

    def _listen(self, settings: LineSettings, seconds: float) -> bytes:
        ser = self.opener(settings)
        try:
            return self._drain(ser, seconds)
        finally:
            ser.close()

    # -- the two phases ----------------------------------------------------
    def _match_continuous(self, data: bytes) -> Optional[tuple[str, list[Reading]]]:
        best = None
        for pid in CONTINUOUS_IDS:
            readings = PROTOCOLS[pid].readings(data)
            numeric = [r for r in readings if r.value is not None or r.overload]
            if len(numeric) < 2:
                continue
            key = (PROTOCOLS[pid].specificity, len(numeric))
            if best is None or key > best[0]:
                best = (key, pid, numeric)
        return (best[1], best[2]) if best else None

    def _passive(self, port: str) -> tuple[Optional[dict], Optional[dict]]:
        """Returns (result, unknown) — `unknown` describes readable data nobody recognised."""
        unknown = None
        for baud in PASSIVE_BAUDS:
            if self.cancelled():
                return None, unknown
            settings = LineSettings(port, baud)
            self.log("listen", port=port, baud=baud, framing="8N1")
            try:
                data = self._listen(settings, self.t.passive_s)
            except Exception as e:                              # noqa: BLE001
                self._step()
                self.log("open_failed", port=port, error=str(e))
                return {"error": str(e)}, None
            self._step()
            if not data:
                continue
            r8, r7 = readability(data), readability(data, mask7=True)
            self.log("heard", port=port, baud=baud, bytes=len(data), readable=round(r8, 2),
                     readable7=round(r7, 2))
            attempts = []
            if r8 >= 0.85:
                attempts.append(("8N1", data))
            elif r7 >= 0.9:
                self.log("seven_bit", port=port, baud=baud)
                for framing in ("7E1", "7O1"):
                    try:
                        seven = self._listen(settings.with_line(baud, framing), self.t.passive_s)
                    except Exception:                           # noqa: BLE001
                        continue
                    attempts.append((framing, seven))
                    break
            else:
                # Framed binary formats can still be found in poorly readable data.
                attempts.append(("8N1", data))
            for framing, sample in attempts:
                match = self._match_continuous(sample)
                if match:
                    pid, readings = match
                    return self._result(port, pid, settings.with_line(baud, framing), readings,
                                        sample, mode="continuous"), None
                if readability(sample) >= 0.85 and unknown is None:
                    unknown = {"baud": baud, "framing": framing, "sample_hex": format_hex(sample[:96]),
                               "sample_text": printable(sample[:96])}
        return None, unknown

    def _active(self, port: str) -> tuple[Optional[dict], Optional[dict]]:
        unknown = None
        for baud, framing in self.active_combos:
            if self.cancelled():
                return None, unknown
            settings = LineSettings(port).with_line(baud, framing)
            try:
                ser = self.opener(settings)
            except Exception as e:                              # noqa: BLE001
                self.log("open_failed", port=port, error=str(e))
                return {"error": str(e)}, None
            try:
                for pid in POLL_IDS:
                    if self.cancelled():
                        return None, unknown
                    proto = PROTOCOLS[pid]
                    self.log("ask", port=port, baud=baud, framing=framing, protocol=pid,
                             request=format_hex(proto.request))
                    reply = self._ask(ser, proto)
                    self._step()
                    if not reply:
                        continue
                    readings = [r for r in proto.readings(reply) if r.value is not None or r.overload]
                    self.log("reply", port=port, protocol=pid, bytes=len(reply),
                             text=printable(reply[:48]), recognised=bool(readings))
                    if readings:
                        again = self._ask(ser, proto, seconds=self.t.confirm_s)
                        confirm = [r for r in proto.readings(again) if r.value is not None or r.overload]
                        if confirm:
                            line = LineSettings(port, baud, request=proto.request,
                                                after_ack=proto.after_ack,
                                                poll_s=proto.default_poll_ms / 1000).with_line(baud, framing)
                            return self._result(port, pid, line, readings + confirm, reply + again,
                                                mode="poll"), None
                    elif unknown is None:
                        unknown = {"baud": baud, "framing": framing, "request": format_hex(proto.request),
                                   "sample_hex": format_hex(reply[:96]), "sample_text": printable(reply[:96])}
            finally:
                ser.close()
        return None, unknown

    def _ask(self, ser: Any, proto, seconds: Optional[float] = None) -> bytes:
        self._drain(ser, self.t.drain_s)
        ser.write(proto.request)
        reply = self._drain(ser, seconds or self.t.probe_s)
        if proto.after_ack and b"\x06" in reply:
            ser.write(proto.after_ack)
            reply += self._drain(ser, seconds or self.t.probe_s)
        return reply

    # -- result ------------------------------------------------------------
    def _result(self, port: str, pid: str, settings: LineSettings, readings: list[Reading],
                sample: bytes, mode: str) -> dict:
        proto = PROTOCOLS[pid]
        latest = readings[-1]
        self.log("found", port=port, protocol=pid, baud=settings.baudrate, framing=settings.framing,
                 value=latest.value, unit=latest.unit)
        return {
            "port": port,
            "found": True,
            "protocol": pid,
            "protocol_name": proto.name,
            "field_tested": proto.field_tested,
            "mode": mode,
            "serial": settings.serial_dict(),
            "exchange": settings.exchange_dict(),
            "readings": [r.as_dict() for r in readings[-6:]],
            "reading": latest.as_dict(),
            "sample_hex": format_hex(sample[:96]),
            "sample_text": printable(sample[:96]),
            "confidence": _confidence(pid, readings),
        }

    def run_port(self, port: str) -> dict:
        self.steps_done = 0
        self.log("port_start", port=port)
        result, unknown = self._passive(port)
        if result and result.get("error"):
            return {"port": port, "found": False, "error": result["error"]}
        if result is None and not self.cancelled():
            result, unknown_active = self._active(port)
            if result and result.get("error"):
                return {"port": port, "found": False, "error": result["error"]}
            unknown = unknown or unknown_active
        if result:
            return result
        self.log("not_found", port=port, heard=bool(unknown))
        return {"port": port, "found": False, "unknown": unknown, "cancelled": self.cancelled()}

    def run(self, ports: list[str]) -> list[dict]:
        results = []
        for port in ports:
            if self.cancelled():
                break
            results.append(self.run_port(port))
        self.log("done", found=sum(1 for r in results if r.get("found")), cancelled=self.cancelled())
        return results
