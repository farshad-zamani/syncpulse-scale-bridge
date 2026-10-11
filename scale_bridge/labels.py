# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani - Cloudtart (https://cloudtart.com)
"""
Scales that send only when Print is pressed — keep listening, keep a log.

Such a scale (typically one wired to a label printer) sends one label per
press and nothing in between, so a label printed while nobody had the port
open would be lost. For every saved profile whose protocol is of that kind,
the bridge keeps the port open all the time and records each label:

    in memory   the last LABELS_KEPT labels per profile  -> GET /labels
    on disk     labels/<profile>-YYYY-MM-DD.jsonl beside bridge.json

Each record: {"seq", "at", "profile", "port", "value", "unit", "fields", "raw_hex"}.
`seq` grows by one per label since the bridge started, so a reader can ask
for "everything after seq N" and never miss or repeat one.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections import deque
from datetime import datetime
from typing import Callable, Optional

from .profiles import line_settings
from .protocols import PROTOCOLS, get_protocol
from .serialio import PortBusy, PortWorker, Registry

log = logging.getLogger("scale_bridge")

LABELS_KEPT = 500
PENDING_MAX = 16 * 1024
KEEP_EVERY_S = 15


def on_print(profile: dict) -> bool:
    proto = PROTOCOLS.get(profile.get("protocol") or "")
    return bool(proto and proto.kind == "print")


class LabelLog:
    def __init__(self, folder: str):
        self.folder = folder
        self.lock = threading.Lock()
        self.records: dict[str, deque] = {}
        self.pending: dict[str, bytes] = {}
        self.seq = 0

    # -- feeding -----------------------------------------------------------
    def feed(self, profile: dict, data: bytes) -> list[dict]:
        """Bytes as they arrive; a label may come in more than one piece."""
        name = profile["name"]
        proto = get_protocol(profile["protocol"], profile.get("params"))
        with self.lock:
            buf = (self.pending.get(name, b"") + data)[-PENDING_MAX:]
            readings = proto.readings(buf)
            end_rx = getattr(proto, "_end", None)
            if readings and end_rx is not None:
                ends = list(end_rx.finditer(buf))
                buf = buf[ends[-1].end():] if ends else b""
            elif readings:
                buf = b""
            self.pending[name] = buf
            out = []
            for r in readings:
                if r.value is None:
                    continue
                self.seq += 1
                rec = {"seq": self.seq, "at": datetime.now().astimezone().isoformat(timespec="seconds"),
                       "profile": name, "port": profile["port"], "value": r.value,
                       "unit": r.unit or profile.get("unit") or "", "fields": dict(r.fields or {}),
                       "raw_hex": r.raw.hex(" ").upper()}
                self.records.setdefault(name, deque(maxlen=LABELS_KEPT)).append(rec)
                out.append(rec)
        for rec in out:
            log.info("label %s: %s %s %s", name, rec["value"], rec["unit"], rec["fields"])
            self._write(rec)
        return out

    def _write(self, rec: dict) -> None:
        try:
            os.makedirs(self.folder, exist_ok=True)
            day = rec["at"][:10]
            safe = re.sub(r"[^A-Za-z0-9_-]", "_", rec["profile"])
            with open(os.path.join(self.folder, f"{safe}-{day}.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("label log not written: %s", e)

    # -- reading -----------------------------------------------------------
    def list(self, profile: Optional[str] = None, after: int = 0, limit: int = 100) -> list[dict]:
        with self.lock:
            names = [profile] if profile else list(self.records)
            items = [r for n in names for r in self.records.get(n, ()) if r["seq"] > after]
        items.sort(key=lambda r: r["seq"])
        return items[-max(1, min(limit, LABELS_KEPT)):]


class Keeper(threading.Thread):
    """Holds the ports of print-only scales open and feeds what they send to the log."""

    def __init__(self, registry: Registry, profiles: Callable[[], list[dict]], labels: LabelLog):
        super().__init__(name="label-keeper", daemon=True)
        self.registry = registry
        self.profiles = profiles
        self.labels = labels
        self._halt = threading.Event()

    def stop(self) -> None:
        self._halt.set()

    def _hook(self, worker: PortWorker, profile: dict) -> None:
        if getattr(worker, "label_profile", None) == profile["name"]:
            return
        worker.listeners.append(lambda t, data, p=profile: self.labels.feed(p, data))
        worker.label_profile = profile["name"]

    def tick(self) -> None:
        for profile in self.profiles():
            if not on_print(profile):
                continue
            try:
                worker = self.registry.worker_for(line_settings(profile))
            except PortBusy:
                continue                        # auto-detection has the port right now
            except Exception as e:              # noqa: BLE001
                log.warning("cannot keep %s open: %s", profile.get("name"), e)
                continue
            self._hook(worker, profile)

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                self.tick()
            except Exception:                   # noqa: BLE001
                log.exception("label keeper")
            self._halt.wait(KEEP_EVERY_S)


def labels_folder(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "labels")

