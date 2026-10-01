# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Simulated scales — every protocol in the library, on a fake COM port.

For trying the program without hardware and for the tests. A simulated
device only understands the speed and framing it was configured with,
exactly like a real one: at another speed a continuous device produces
garbage and a polled one stays silent; a 7E1 device read as 8N1 shows its
parity bit in the top bit of each byte.

    --simulate mahak_mds                       COM90, 9600 8N1
    --simulate toledo_cont:4800:7E1,mt_sics    COM90 and COM91
"""
from __future__ import annotations

import time
from typing import Optional

from .serialio import LineSettings, Opener, open_real

FIRST_PORT = 90

# The weight walks through an empty scale, 550 g, a ~13 kg package that
# settles, and 750 g — (seconds, [kg values], stable).
SCHEDULE = [(6, [0.0], True), (8, [0.55], True), (3, [12.85, 13.15, 13.10], False),
            (8, [13.05], True), (6, [0.75], True)]


def weight_now(t0: float) -> tuple[float, bool]:
    total = sum(s for s, _, _ in SCHEDULE)
    t = (time.monotonic() - t0) % total
    for seconds, values, stable in SCHEDULE:
        if t < seconds:
            return values[int(t * 3) % len(values)], stable
        t -= seconds
    return 0.0, True


def _even_parity_bit(b: int) -> int:
    return (bin(b & 0x7F).count("1") & 1) << 7


def frame_for(protocol: str, kg: float, stable: bool) -> bytes:
    """What `protocol` sends for `kg` — the same shapes the parsers read."""
    if protocol == "mt_sics":
        return f"S {'S' if stable else 'D'} {kg:10.3f} kg\r\n".encode()
    if protocol == "and_std":
        return f"{'ST' if stable else 'US'},GS,{kg:+09.3f}kg\r\n".encode()
    if protocol == "toledo_cont":
        digits = f"{round(abs(kg) * 1000):06d}".encode()
        swa = 0x20 | 0x08 | 5                   # count-by x1, 0.00X
        swb = 0x20 | 0x10 | (0 if stable else 0x08) | (0x02 if kg < 0 else 0)
        swc = 0x20
        body = bytes([0x02, swa, swb, swc]) + digits + b"000000" + b"\r"
        return body + bytes([(-sum(b & 0x7F for b in body)) & 0x7F])
    if protocol == "sma":
        return b"\n 1G" + (b" " if stable else b"M") + b" " + f"{kg:10.3f}".encode() + b"kg \r"
    if protocol == "nci":
        return b"\n" + f"{kg:8.3f}kg".encode() + b"\r\n" + (b"0" if stable else b"1") + b"0\r\x03"
    if protocol == "ohaus":
        return f"{kg:10.3f} kg{'' if stable else ' ?'}\r\n".encode()
    if protocol == "sartorius":
        return f"+{kg:10.3f} {'kg' if stable else '  '}\r\n".encode()
    if protocol == "cas_enq":
        return b"\x01\x02" + (b"S" if stable else b"U") + f" {kg:7.3f}kg".encode() + b"\x03\x04"
    if protocol == "xk3190_tf0":
        body = (b"-" if kg < 0 else b"+") + f"{round(abs(kg) * 1000):06d}".encode() + b"3"
        x = 0
        for b in body:
            x ^= b
        return b"\x02" + body + f"{x >> 4:X}{x & 0xF:X}".encode() + b"\x03"
    if protocol == "xk3190_reversed":
        return f"{kg:08.3f}"[::-1].encode() + b"="
    if protocol == "mahak_mds":
        grams = round(kg * 1000)
        return bytes([0x58, (grams * 7 + 0x51) & 0xFF, 0x07, 0x07]) + grams.to_bytes(3, "big")
    return f"G  {kg:.3f} kg\r\n".encode()


class SimulatedDevice:
    """Quacks like a pyserial Serial for what the bridge uses."""

    CONTINUOUS = {"toledo_cont", "xk3190_tf0", "xk3190_reversed", "ascii_generic"}
    REQUESTS = {"mt_sics": b"SI\r\n", "and_std": b"Q\r\n", "sma": b"\nW\r", "nci": b"W\r",
                "ohaus": b"IP\r\n", "sartorius": b"\x1bP\r\n", "mahak_mds": bytes.fromhex("4D090407"),
                "cas_enq": b"\x05"}
    BOOT = bytes.fromhex("42 03 04 01 42 4F 4F 54 0C 04 8C")

    def __init__(self, protocol: str, baudrate: int, framing: str, opened: LineSettings):
        self.protocol = protocol
        self.device_baud = baudrate
        self.device_framing = framing
        self.opened = opened
        self.is_open = True
        self._t0 = time.monotonic()
        self._out = bytearray()
        self._due: list[tuple[float, bytes]] = []
        self._next_emit = time.monotonic()
        self._next_boot = time.monotonic() + 60
        self._garbage_seed = 0x5A

    # -- line matching -----------------------------------------------------
    @property
    def _baud_ok(self) -> bool:
        return self.opened.baudrate == self.device_baud

    @property
    def _framing_ok(self) -> bool:
        return self.opened.framing == self.device_framing

    def _as_received(self, data: bytes) -> bytes:
        """What the host's UART makes of the device's bytes."""
        if not self._baud_ok:
            out = bytearray()
            for _ in range(max(1, len(data) // 3)):
                self._garbage_seed = (self._garbage_seed * 73 + 41) & 0xFF
                out.append(self._garbage_seed | 0x80)
            return bytes(out)
        if self._framing_ok:
            return data
        if self.device_framing.startswith("7") and self.opened.bytesize == 8:
            return bytes((b & 0x7F) | _even_parity_bit(b) for b in data)
        if self.device_framing.startswith("8") and self.opened.bytesize == 7:
            return bytes(b & 0x7F for b in data)
        return data

    # -- pyserial surface --------------------------------------------------
    def _pump(self) -> None:
        now = time.monotonic()
        if self.protocol in self.CONTINUOUS and now >= self._next_emit:
            kg, stable = weight_now(self._t0)
            self._out += self._as_received(frame_for(self.protocol, kg, stable))
            self._next_emit = now + 0.2
        if self.protocol == "mahak_mds" and now >= self._next_boot:
            self._out += self._as_received(self.BOOT)
            self._next_boot = now + 60
        ready = [d for d in self._due if d[0] <= now]
        self._due = [d for d in self._due if d[0] > now]
        for _, data in ready:
            self._out += self._as_received(data)

    def write(self, data: bytes) -> int:
        if not (self._baud_ok and self._framing_ok):
            return len(data)
        data = bytes(data)
        request = self.REQUESTS.get(self.protocol)
        kg, stable = weight_now(self._t0)
        if self.protocol == "cas_enq":
            if b"\x05" in data:
                self._due.append((time.monotonic() + 0.03, b"\x06"))
            if b"\x11" in data:
                self._due.append((time.monotonic() + 0.04, frame_for("cas_enq", kg, stable)))
        elif request and request in data:
            self._due.append((time.monotonic() + 0.04, frame_for(self.protocol, kg, stable)))
        return len(data)

    @property
    def in_waiting(self) -> int:
        self._pump()
        return len(self._out)

    def read(self, n: int = 1) -> bytes:
        self._pump()
        if not self._out:
            time.sleep(0.02)
            self._pump()
        chunk = bytes(self._out[:n])
        del self._out[:n]
        return chunk

    def reset_input_buffer(self) -> None:
        self._out.clear()

    def close(self) -> None:
        self.is_open = False


class SimulatorBank:
    """Fake ports COM90, COM91 …; every other port opens for real."""

    def __init__(self, spec: str):
        self.devices: dict[str, tuple[str, int, str]] = {}
        for i, item in enumerate(filter(None, (s.strip() for s in spec.split(",")))):
            parts = item.split(":")
            protocol = parts[0]
            baud = int(parts[1]) if len(parts) > 1 and parts[1] else 9600
            framing = (parts[2] if len(parts) > 2 and parts[2] else "8N1").upper()
            self.devices[f"COM{FIRST_PORT + i}"] = (protocol, baud, framing)

    def opener(self, fallback: Optional[Opener] = None) -> Opener:
        real = fallback or open_real

        def _open(settings: LineSettings):
            device = self.devices.get(settings.port.upper())
            if device is None:
                return real(settings)
            return SimulatedDevice(device[0], device[1], device[2], settings)
        return _open

    def ports(self) -> list[dict]:
        return [{"device": port, "description": f"Simulated scale ({proto}, {baud} {framing})",
                 "hwid": "SIMULATED", "vid": None, "pid": None, "manufacturer": "simulator",
                 "chip": None, "note": "", "kind": "simulated"}
                for port, (proto, baud, framing) in self.devices.items()]
