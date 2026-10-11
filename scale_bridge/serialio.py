# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Serial ports: listing them, describing a line, and keeping one open.

A `PortWorker` owns one COM port. While somebody keeps asking for data it
holds the port open, sends the request (if the device must be asked) at
the poll interval, cuts what comes back into chunks at silences, and keeps
the recent chunks. Unplugging the USB cable, a driver hiccup or a busy port
are all survived: the worker closes, waits, and opens again.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Optional

try:
    import serial
    from serial.tools import list_ports as _list_ports
except ImportError:                                            # pragma: no cover
    serial = None
    _list_ports = None

log = logging.getLogger("scale_bridge")

RING_SIZE = 64            # chunks kept per port
MAX_CHUNK = 512           # a continuous stream without silences is cut here
IDLE_CLOSE_S = 120        # a port nobody asked about for this long is released
MAX_REQUEST_BYTES = 64

_PORT_RE = re.compile(r"^(COM\d{1,3}|/dev/[A-Za-z0-9_./-]+)$", re.IGNORECASE)

# USB-serial chips worth a word to the person choosing a port.
KNOWN_CHIPS: dict[int, tuple[str, str]] = {
    0x1A86: ("WCH CH340/CH341",
             "Clone CH340 chips fail with WCH drivers 3.8 and newer on Windows "
             "('A device attached to the system is not functioning'). Install driver "
             "3.5.2019.1 or use an FTDI-based adapter."),
    0x067B: ("Prolific PL2303",
             "Counterfeit PL2303 chips are refused by newer Prolific drivers (Code 10). "
             "Use an older driver or an FTDI-based adapter."),
    0x0403: ("FTDI", ""),
    0x10C4: ("Silicon Labs CP210x", ""),
    0x0557: ("ATEN", ""),
    0x110A: ("Moxa", ""),
}


def now_ms() -> int:
    return int(time.monotonic() * 1000)


def parse_hex(text: str) -> bytes:
    """'4d0904 07', '0x4D 0x09', '4D-09' -> bytes. Raises ValueError."""
    cleaned = re.sub(r"0x", "", str(text or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"[\s,;:-]+", "", cleaned)
    return bytes.fromhex(cleaned)


def format_hex(data: bytes) -> str:
    return data.hex(" ").upper()


def printable(data: bytes) -> str:
    names = {0x02: "<STX>", 0x03: "<ETX>", 0x0D: "<CR>", 0x0A: "<LF>", 0x05: "<ENQ>",
             0x06: "<ACK>", 0x15: "<NAK>", 0x1B: "<ESC>", 0x11: "<DC1>"}
    out = []
    for b in data:
        if b in names:
            out.append(names[b])
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"<{b:02X}>")
    return "".join(out)


# ---------------------------------------------------------------------------
# One line's settings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LineSettings:
    port: str
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1
    dtr: bool = True
    rts: bool = True
    request: bytes = b""       # sent every poll interval; empty = only listen
    after_ack: bytes = b""     # sent when the device answers the request with ACK
    poll_s: float = 0.5
    gap_s: float = 0.05        # silence that ends a chunk

    @property
    def framing(self) -> str:
        stop = int(self.stopbits) if self.stopbits in (1, 2) else self.stopbits
        return f"{self.bytesize}{self.parity}{stop}"

    def describe(self) -> str:
        req = f", request {format_hex(self.request)}" if self.request else ", listen only"
        return f"{self.port} {self.baudrate} {self.framing}{req}"

    def with_line(self, baudrate: int, framing: str) -> "LineSettings":
        bits, parity, stop = int(framing[0]), framing[1], float(framing[2:])
        return LineSettings(self.port, baudrate, bits, parity, stop, self.dtr, self.rts,
                            self.request, self.after_ack, self.poll_s, self.gap_s)

    def serial_dict(self) -> dict[str, Any]:
        stop = int(self.stopbits) if self.stopbits in (1, 2) else self.stopbits
        return {"port": self.port, "baudrate": self.baudrate, "bytesize": self.bytesize,
                "parity": self.parity, "stopbits": stop, "dtr": self.dtr, "rts": self.rts}

    def exchange_dict(self) -> dict[str, Any]:
        return {"request_hex": format_hex(self.request),
                "after_ack_hex": format_hex(self.after_ack),
                "poll_interval_ms": int(round(self.poll_s * 1000)),
                "frame_gap_ms": int(round(self.gap_s * 1000))}

    @classmethod
    def from_dicts(cls, serial_cfg: dict, exchange_cfg: Optional[dict] = None,
                   port: Optional[str] = None) -> "LineSettings":
        """Validate settings that arrive over the network or from a file."""
        exchange_cfg = exchange_cfg or {}
        name = str(port or serial_cfg.get("port") or "").strip()
        if not _PORT_RE.match(name):
            raise ValueError(f"invalid port name: {name!r}")
        if name.upper().startswith("COM"):
            name = name.upper()
        baudrate = int(serial_cfg.get("baudrate") or 9600)
        if not 50 <= baudrate <= 921600:
            raise ValueError(f"invalid baudrate: {baudrate}")
        bytesize = int(serial_cfg.get("bytesize") or 8)
        if bytesize not in (5, 6, 7, 8):
            raise ValueError(f"invalid bytesize: {bytesize}")
        parity = str(serial_cfg.get("parity") or "N").upper()[:1]
        if parity not in "NEOMS":
            raise ValueError(f"invalid parity: {parity}")
        stopbits = float(serial_cfg.get("stopbits") or 1)
        if stopbits not in (1, 1.5, 2):
            raise ValueError(f"invalid stopbits: {stopbits}")
        try:
            request = parse_hex(exchange_cfg.get("request_hex") or "")
            after_ack = parse_hex(exchange_cfg.get("after_ack_hex") or "")
        except ValueError as e:
            raise ValueError(f"invalid request hex: {e}") from e
        if len(request) > MAX_REQUEST_BYTES or len(after_ack) > MAX_REQUEST_BYTES:
            raise ValueError("request too long")
        poll_ms = min(max(int(exchange_cfg.get("poll_interval_ms") or 500), 100), 10000)
        gap_ms = min(max(int(exchange_cfg.get("frame_gap_ms") or 50), 5), 1000)
        return cls(port=name, baudrate=baudrate, bytesize=bytesize, parity=parity,
                   stopbits=int(stopbits) if stopbits in (1, 2) else stopbits,
                   dtr=bool(serial_cfg.get("dtr", True)), rts=bool(serial_cfg.get("rts", True)),
                   request=request, after_ack=after_ack,
                   poll_s=poll_ms / 1000, gap_s=gap_ms / 1000)


# ---------------------------------------------------------------------------
# Opening and listing
# ---------------------------------------------------------------------------

Opener = Callable[[LineSettings], Any]


def open_real(s: LineSettings) -> Any:
    if serial is None:
        raise RuntimeError("pyserial is not installed")
    ser = serial.Serial(port=s.port, baudrate=s.baudrate, bytesize=s.bytesize,
                        parity=s.parity, stopbits=s.stopbits, timeout=0.02, write_timeout=1.0)
    ser.dtr = s.dtr
    ser.rts = s.rts
    ser.reset_input_buffer()
    return ser


def _port_sort_key(name: str) -> tuple:
    m = re.match(r"^COM(\d+)$", name, re.IGNORECASE)
    return (0, int(m.group(1)), "") if m else (1, 0, name)


def list_serial_ports() -> list[dict[str, Any]]:
    if _list_ports is None:
        return []
    out = []
    for p in _list_ports.comports():
        chip, note = KNOWN_CHIPS.get(p.vid, (None, "")) if p.vid is not None else (None, "")
        text = f"{p.description or ''} {p.hwid or ''}".lower()
        kind = "bluetooth" if ("bluetooth" in text or "bthenum" in text) else (
            "usb" if p.vid is not None else "native")
        out.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "vid": f"{p.vid:04X}" if p.vid is not None else None,
            "pid": f"{p.pid:04X}" if p.pid is not None else None,
            "manufacturer": p.manufacturer,
            "chip": chip,
            "note": note,
            "kind": kind,
        })
    return sorted(out, key=lambda p: _port_sort_key(p["device"]))


# ---------------------------------------------------------------------------
# A worker per port
# ---------------------------------------------------------------------------

class PortWorker(threading.Thread):
    def __init__(self, settings: LineSettings, opener: Opener):
        super().__init__(name=f"port-{settings.port}", daemon=True)
        self.settings = settings
        self.opener = opener
        self.chunks: deque[tuple[int, bytes]] = deque(maxlen=RING_SIZE)
        self.cond = threading.Condition()
        self.ser: Any = None
        self.last_error: Optional[str] = None
        self.last_used = time.monotonic()
        self.first_attempt = threading.Event()
        self._halt = threading.Event()
        # Called with (t_ms, bytes) for every chunk, outside the lock.
        self.listeners: list[Callable[[int, bytes], None]] = []
        self.stats = {"opened_at": None, "bytes_rx": 0, "frames_rx": 0, "requests_tx": 0,
                      "open_failures": 0}

    # -- lifecycle ---------------------------------------------------------
    def touch(self) -> None:
        self.last_used = time.monotonic()

    def stop(self) -> None:
        self._halt.set()

    @property
    def stopped(self) -> bool:
        return self._halt.is_set()

    def _open(self) -> bool:
        try:
            self.ser = self.opener(self.settings)
            self.last_error = None
            self.stats["opened_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            log.info("%s opened", self.settings.describe())
            return True
        except Exception as e:                                  # noqa: BLE001
            self.ser = None
            self.stats["open_failures"] += 1
            message = f"could not open port {self.settings.port}: {e}"
            if message != self.last_error:
                log.warning("%s", message)
            self.last_error = message
            return False
        finally:
            self.first_attempt.set()
            with self.cond:
                self.cond.notify_all()

    def _close(self) -> None:
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:                                   # noqa: BLE001
                pass
            self.ser = None

    def _push(self, data: bytes, t_ms: int) -> None:
        with self.cond:
            self.chunks.append((t_ms, data))
            self.stats["frames_rx"] += 1
            self.cond.notify_all()
        for listener in list(self.listeners):
            try:
                listener(t_ms, data)
            except Exception:                                   # noqa: BLE001
                log.exception("chunk listener failed")

    def run(self) -> None:
        s = self.settings
        buf = bytearray()
        last_rx = 0.0
        next_request = 0.0
        while not self._halt.is_set():
            if time.monotonic() - self.last_used > IDLE_CLOSE_S:
                log.info("%s idle for %ds, released", s.port, IDLE_CLOSE_S)
                break
            if self.ser is None:
                if not self._open():
                    self._halt.wait(2.0)
                    continue
                buf.clear()
                next_request = 0.0
            try:
                now = time.monotonic()
                if s.request and now >= next_request:
                    self.ser.write(s.request)
                    self.stats["requests_tx"] += 1
                    next_request = now + s.poll_s
                waiting = self.ser.in_waiting
                chunk = self.ser.read(waiting if waiting else 1)
                now = time.monotonic()
                if chunk:
                    if s.after_ack and b"\x06" in chunk:
                        self.ser.write(s.after_ack)
                    buf += chunk
                    last_rx = now
                    self.stats["bytes_rx"] += len(chunk)
                    if len(buf) >= MAX_CHUNK:
                        self._push(bytes(buf), int(now * 1000))
                        buf.clear()
                    continue
                if buf and now - last_rx >= s.gap_s:
                    self._push(bytes(buf), int(last_rx * 1000))
                    buf.clear()
            except Exception as e:                              # noqa: BLE001
                self.last_error = f"{s.port}: {e.__class__.__name__}: {e}"
                log.warning("%s lost: %s", s.port, e)
                self._close()
                self._halt.wait(1.0)
        self._close()
        self._halt.set()
        with self.cond:
            self.cond.notify_all()

    # -- reading -----------------------------------------------------------
    def wait_fresh(self, max_age_ms: int, wait_ms: int) -> None:
        """Return once a chunk younger than max_age_ms exists, or wait_ms passed."""
        self.first_attempt.wait(timeout=min(wait_ms, 3000) / 1000)
        deadline = time.monotonic() + wait_ms / 1000
        with self.cond:
            while True:
                if self.chunks and now_ms() - self.chunks[-1][0] <= max_age_ms:
                    return
                if self.ser is None and self.last_error:
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._halt.is_set():
                    return
                self.cond.wait(timeout=remaining)

    def recent(self, count: int) -> list[tuple[int, bytes]]:
        with self.cond:
            return list(self.chunks)[-count:] if count > 0 else []

    @property
    def is_open(self) -> bool:
        return self.ser is not None

    def snapshot(self, count: int) -> dict[str, Any]:
        chunks = self.recent(count)
        is_open = self.is_open
        return {
            "ok": is_open or bool(chunks and not self.last_error),
            "open": is_open,
            "error": None if is_open else self.last_error,
            "now": now_ms(),
            "port": self.settings.port,
            "frames": [{"t": t, "hex": format_hex(d)} for t, d in chunks],
            "stats": dict(self.stats),
        }


class PortBusy(RuntimeError):
    """The port is reserved (auto-detection is running on it)."""


def port_key(port: str) -> str:
    return port.upper() if port.upper().startswith("COM") else port


class Registry:
    """At most one worker per port; new settings for a port reopen it."""

    def __init__(self, opener: Opener):
        self.opener = opener
        self.lock = threading.Lock()
        self.workers: dict[str, PortWorker] = {}
        self.reserved: set[str] = set()

    def reserve(self, ports: list[str]) -> None:
        """Close these ports and keep them closed until `unreserve` (for auto-detection)."""
        with self.lock:
            self.reserved.update(port_key(p) for p in ports)
        for p in ports:
            self.release(p)

    def unreserve(self, ports: list[str]) -> None:
        with self.lock:
            self.reserved.difference_update(port_key(p) for p in ports)

    def worker_for(self, settings: LineSettings) -> PortWorker:
        with self.lock:
            if port_key(settings.port) in self.reserved:
                raise PortBusy(f"{settings.port} is busy: auto-detection is running on it")
            current = self.workers.get(settings.port)
            if current is not None and (current.stopped or current.settings != settings):
                if not current.stopped:
                    log.info("%s settings changed, reopening", settings.port)
                current.stop()
                current.join(timeout=3)
                current = None
            if current is None:
                current = PortWorker(settings, self.opener)
                self.workers[settings.port] = current
                current.start()
            current.touch()
            return current

    def release(self, port: str) -> None:
        """Close a port so something else (auto-detect) can open it."""
        with self.lock:
            worker = self.workers.pop(port_key(port), None)
        if worker is not None:
            worker.stop()
            worker.join(timeout=3)

    def active_ports(self) -> list[str]:
        with self.lock:
            return [p for p, w in self.workers.items() if not w.stopped]

    def stop_all(self) -> None:
        with self.lock:
            workers = list(self.workers.values())
            self.workers.clear()
        for w in workers:
            w.stop()
        for w in workers:
            w.join(timeout=3)
