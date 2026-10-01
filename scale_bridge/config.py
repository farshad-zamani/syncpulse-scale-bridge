# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
bridge.json — the bridge's settings, access key and saved scale profiles.

It lives beside the program, so copying the folder copies the setup. When
that folder is read-only (e.g. Program Files), %LOCALAPPDATA% is used.
Files written by the earlier SyncPulse Serial Bridge are read as they are.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import sys
import tempfile
import threading
from typing import Any, Optional

from . import EXE_NAME
from .profiles import MAX_PROFILES, validate

log = logging.getLogger("scale_bridge")

DEFAULT_PORT = 8765
DEFAULTS: dict[str, Any] = {
    "listen_host": "0.0.0.0",
    "listen_port": DEFAULT_PORT,
    "token": "",
    # Empty = any machine that has the key. Put the platform server's IP here
    # to refuse everybody else, e.g. ["192.168.1.10"].
    "allowed_clients": [],
    "profiles": [],
}


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _writable(directory: str) -> bool:
    try:
        fd, probe = tempfile.mkstemp(prefix=".write-test-", dir=directory)
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        return False


def default_path() -> str:
    beside = os.path.join(app_dir(), "bridge.json")
    if os.path.exists(beside) or _writable(app_dir()):
        return beside
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    folder = os.path.join(base, EXE_NAME)
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "bridge.json")


def new_token() -> str:
    return secrets.token_urlsafe(24)


class Config:
    def __init__(self, path: Optional[str] = None):
        self.path = os.path.abspath(path or default_path())
        self.lock = threading.RLock()
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # -- file --------------------------------------------------------------
    def load(self) -> None:
        with self.lock:
            data = dict(DEFAULTS)
            if os.path.exists(self.path):
                try:
                    with open(self.path, encoding="utf-8-sig") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data.update(loaded)
                except (OSError, ValueError) as e:
                    backup = self.path + ".broken"
                    log.error("%s could not be read (%s); kept as %s and started fresh", self.path, e,
                              backup)
                    try:
                        os.replace(self.path, backup)
                    except OSError:
                        pass
            profiles = []
            for raw in data.get("profiles") or []:
                try:
                    profiles.append(validate(raw))
                except (ValueError, TypeError, KeyError) as e:
                    log.warning("profile %r ignored: %s", (raw or {}).get("name"), e)
            data["profiles"] = profiles
            self.data = data
            if not data.get("token"):
                data["token"] = new_token()
                self.save()
                log.info("created %s with a new access key", self.path)

    def save(self) -> None:
        with self.lock:
            folder = os.path.dirname(self.path)
            os.makedirs(folder, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".bridge-", suffix=".json", dir=folder)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, indent=2, ensure_ascii=False)
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise

    # -- values ------------------------------------------------------------
    @property
    def token(self) -> str:
        return str(self.data.get("token") or "")

    def rotate_token(self) -> str:
        with self.lock:
            self.data["token"] = new_token()
            self.save()
            return self.token

    @property
    def listen_host(self) -> str:
        return str(self.data.get("listen_host") or "0.0.0.0")

    @property
    def listen_port(self) -> int:
        try:
            return int(self.data.get("listen_port") or DEFAULT_PORT)
        except (TypeError, ValueError):
            return DEFAULT_PORT

    @property
    def allowed_clients(self) -> list[str]:
        value = self.data.get("allowed_clients") or []
        return [str(v).strip() for v in value if str(v).strip()] if isinstance(value, list) else []

    def set_allowed_clients(self, clients: list[str]) -> None:
        import ipaddress
        cleaned = []
        for c in clients:
            c = str(c).strip()
            if not c:
                continue
            ipaddress.ip_address(c)                 # raises ValueError
            cleaned.append(c)
        with self.lock:
            self.data["allowed_clients"] = cleaned
            self.save()

    # -- profiles ----------------------------------------------------------
    def profiles(self) -> list[dict]:
        with self.lock:
            return [dict(p) for p in self.data.get("profiles") or []]

    def profile(self, name: str) -> Optional[dict]:
        name = str(name or "").strip().lower()
        with self.lock:
            for p in self.data.get("profiles") or []:
                if p["name"].lower() == name:
                    return dict(p)
        return None

    def save_profile(self, raw: dict) -> dict:
        profile = validate(raw)
        with self.lock:
            items = [p for p in self.data.get("profiles") or []
                     if p["name"].lower() != profile["name"].lower()]
            if len(items) >= MAX_PROFILES:
                raise ValueError(f"at most {MAX_PROFILES} profiles")
            items.append(profile)
            self.data["profiles"] = items
            self.save()
        return profile

    def delete_profile(self, name: str) -> bool:
        with self.lock:
            items = self.data.get("profiles") or []
            kept = [p for p in items if p["name"].lower() != str(name).lower()]
            if len(kept) == len(items):
                return False
            self.data["profiles"] = kept
            self.save()
            return True
