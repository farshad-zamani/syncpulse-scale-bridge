# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Profiles: a saved answer to "how does the scale on this port talk".

A profile is what auto-detection found (or what was set by hand): the port,
the line settings, the request, and the protocol that reads the reply. The
bridge keeps profiles in bridge.json; anybody on the network with the access
key can then ask `/weight?profile=<name>` and get a finished number.

    {
      "name": "packing-1",           letters, digits, - and _
      "label": "Packing line scale",
      "port": "COM7",
      "protocol": "mahak_mds",
      "params": {},                  only for custom_binary / custom_ascii
      "serial": {...},               LineSettings.serial_dict()
      "exchange": {...},             LineSettings.exchange_dict()
      "unit": "",                    the unit when the frames carry none
      "output_unit": "",             convert to this unit ("" = as sent)
      "stable_samples": 3            equal readings in a row = stable, when
                                     the protocol has no stability flag
    }
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from .protocols import GRAMS_PER, PROTOCOLS, Reading, convert, get_protocol, norm_unit
from .serialio import LineSettings, PortWorker

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$")
MAX_PROFILES = 64
RECENT_CHUNKS = 24


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "-", str(text or "")).strip("-_").lower()
    return (s or "scale")[:40]


def validate(raw: dict) -> dict:
    """Check a profile that arrives from the user interface or from bridge.json."""
    if not isinstance(raw, dict):
        raise ValueError("profile must be an object")
    name = str(raw.get("name") or "").strip()
    if not NAME_RE.match(name):
        raise ValueError("profile name: 1-40 letters, digits, '-' or '_', starting with a letter or digit")
    protocol = str(raw.get("protocol") or "")
    if protocol not in PROTOCOLS:
        raise ValueError(f"unknown protocol: {protocol!r}")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    if protocol == "custom_ascii":
        try:
            re.compile(str(params.get("regex") or "").encode("latin-1"))
        except (re.error, UnicodeEncodeError) as e:
            raise ValueError(f"invalid regular expression: {e}") from e
        if not params.get("regex"):
            raise ValueError("custom_ascii needs a regular expression")
    serial_cfg = dict(raw.get("serial") or {})
    port = str(raw.get("port") or serial_cfg.get("port") or "")
    line = LineSettings.from_dicts(serial_cfg, raw.get("exchange") or {}, port=port)
    unit = norm_unit(raw.get("unit") or "")
    output_unit = norm_unit(raw.get("output_unit") or "")
    if output_unit and output_unit not in GRAMS_PER:
        raise ValueError(f"unknown unit: {output_unit!r}")
    stable_samples = min(max(int(raw.get("stable_samples") or 3), 1), 20)
    return {
        "name": name,
        "label": str(raw.get("label") or "")[:80],
        "port": line.port,
        "protocol": protocol,
        "params": {k: params[k] for k in ("pattern", "value_offset", "value_length", "byte_order",
                                           "signed", "regex", "unit") if k in params},
        "serial": line.serial_dict(),
        "exchange": line.exchange_dict(),
        "unit": unit,
        "output_unit": output_unit,
        "stable_samples": stable_samples,
        "created": str(raw.get("created") or datetime.now().astimezone().isoformat(timespec="seconds")),
    }


def from_detection(result: dict, name: str, label: str = "") -> dict:
    return validate({
        "name": name,
        "label": label,
        "port": result["port"],
        "protocol": result["protocol"],
        "serial": result["serial"],
        "exchange": result["exchange"],
        "unit": "" if (result.get("reading") or {}).get("unit") else "kg",
    })


def line_settings(profile: dict) -> LineSettings:
    return LineSettings.from_dicts(profile["serial"], profile.get("exchange") or {},
                                   port=profile["port"])


# ---------------------------------------------------------------------------
# Turning the bytes a worker holds into one answer
# ---------------------------------------------------------------------------

@dataclass
class Timed:
    t_ms: int
    reading: Reading


def timed_readings(protocol_id: str, params: Optional[dict],
                   chunks: list[tuple[int, bytes]]) -> list[Timed]:
    proto = get_protocol(protocol_id, params)
    out: list[Timed] = []
    if proto.kind == "print":
        # A label can arrive in more than one chunk: read them joined, and
        # date each reading by the chunk that completed it.
        buf = b""
        seen = 0
        for t, data in chunks:
            buf += data
            found = proto.readings(buf)
            out.extend(Timed(t, r) for r in found[seen:])
            seen = len(found)
        return out
    for t, data in chunks:
        for r in proto.readings(data):
            out.append(Timed(t, r))
    return out


def evaluate(profile: dict, worker: PortWorker, max_age_ms: int, now: int) -> dict[str, Any]:
    """The newest reading, with its stability and unit settled."""
    readings = timed_readings(profile["protocol"], profile.get("params"), worker.recent(RECENT_CHUNKS))
    printing = is_on_print(profile)
    base = {"ok": False, "profile": profile.get("name"), "port": profile["port"],
            "protocol": profile["protocol"], "open": worker.is_open, "on_print": printing}
    if not readings:
        if not worker.is_open:
            return {**base, "error": worker.last_error or "port is not open"}
        if printing:
            return {**base, "error": "waiting for the Print key on the scale"}
        return {**base, "error": "no data from the scale yet" if not worker.recent(1) else
                "data arrives but no weight could be read from it — check the protocol"}
    latest = readings[-1]
    age = now - latest.t_ms
    reading = latest.reading
    stale = age > max_age_ms
    if reading.value is None:
        return {**base, "ok": True, "value": None, "unit": reading.unit, "stable": False,
                "overload": reading.overload, "age_ms": age, "stale": stale,
                "raw_hex": reading.raw.hex(" ").upper()}

    stable = reading.stable
    if stable is None:
        # No stability flag in this protocol: the same value several times in
        # a row, all of them recent, counts as stable.
        need = int(profile.get("stable_samples") or 3)
        poll_ms = int((profile.get("exchange") or {}).get("poll_interval_ms") or 500)
        window = max_age_ms + need * max(poll_ms, 250) * 2
        tail = [x.reading.value for x in readings[-need:] if now - x.t_ms <= window]
        stable = len(tail) >= need and all(v == tail[-1] for v in tail)
    unit = reading.unit or profile.get("unit") or ""
    value = reading.value
    output_unit = profile.get("output_unit") or ""
    if output_unit and unit and output_unit != unit:
        converted = convert(value, unit, output_unit)
        if converted is not None:
            value, unit = round(converted, 6), output_unit
    measured = datetime.now().astimezone().timestamp() - age / 1000
    return {
        **base,
        "ok": True,
        "value": value,
        "unit": unit,
        "stable": bool(stable) and not stale,
        "net": reading.net,
        "overload": reading.overload,
        "age_ms": age,
        "stale": stale,
        "measured_at": datetime.fromtimestamp(measured).astimezone().isoformat(timespec="milliseconds"),
        "raw_hex": reading.raw.hex(" ").upper(),
        "checksum_ok": reading.checksum_ok,
        # e.g. order number, shift and date printed on a label
        "fields": dict(reading.fields or {}),
    }


def ad_hoc(port: str, protocol: str, serial_cfg: Optional[dict] = None,
           exchange_cfg: Optional[dict] = None, params: Optional[dict] = None) -> dict:
    """A throw-away profile for `/weight?port=...` without a saved profile."""
    proto = PROTOCOLS.get(protocol)
    if proto is None:
        raise ValueError(f"unknown protocol: {protocol!r}")
    exchange = dict(exchange_cfg or {})
    if "request_hex" not in exchange:
        exchange["request_hex"] = proto.request.hex(" ")
        exchange["after_ack_hex"] = proto.after_ack.hex(" ")
        exchange.setdefault("poll_interval_ms", proto.default_poll_ms)
    return validate({"name": "adhoc", "port": port, "protocol": protocol, "params": params or {},
                     "serial": serial_cfg or {}, "exchange": exchange})


def is_on_print(profile: dict) -> bool:
    proto = PROTOCOLS.get(profile.get("protocol") or "")
    return bool(proto and proto.kind == "print")


def wait_for_reading(profile: dict, worker: PortWorker, max_age_ms: int, wait_ms: int,
                     now_fn) -> dict[str, Any]:
    """Wait (up to wait_ms) until the newest reading is fresh, then evaluate."""
    if is_on_print(profile):
        # Nothing comes until somebody presses Print: do not hold the caller.
        wait_ms = min(wait_ms, 400)
    deadline = time.monotonic() + wait_ms / 1000
    while True:
        worker.wait_fresh(max_age_ms, int(max(0.0, deadline - time.monotonic()) * 1000))
        result = evaluate(profile, worker, max_age_ms, now_fn())
        if result.get("ok") and not result.get("stale"):
            return result
        if time.monotonic() >= deadline or (not worker.is_open and worker.last_error):
            return result
        # Data arrived but held no reading (a partial frame, a boot message …).
        time.sleep(0.05)
