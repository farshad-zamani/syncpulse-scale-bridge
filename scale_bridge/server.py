# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
The HTTP side of the bridge.

For the network (the SyncPulse platform or any other system) — JSON, and
the header `X-Bridge-Token: <access key>` on everything except /health:

    GET  /health                       service, version, host (no key needed)
    GET  /ports                        COM ports on this PC
    POST /read                         raw frames for given line settings
                                       (the contract of SyncPulse Serial Bridge 1.x)
    GET  /profiles                     saved scale profiles
    GET  /weight?profile=NAME          the current weight, parsed and checked
    GET  /weight?port=COM7&protocol=mt_sics[&baud=9600&framing=8N1]
    POST /weight                       {"profile": NAME} or a whole profile

For the page on this PC only (loopback address, and the header
`X-Requested-With: ScaleBridge` so another web page cannot drive it):

    GET  /                             the user interface
    GET  /api/state, /api/protocols, /api/weight, /api/monitor
    POST /api/detect, /api/detect/cancel, /api/profiles, /api/token,
         /api/allowed, /api/firewall, /api/autostart
    GET  /api/detect                   progress and results of auto-detection
    DELETE /api/profiles/NAME
"""
from __future__ import annotations

import hmac
import json
import logging
import socket
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from . import ABOUT, PRODUCT, SERVICE_ID, __version__, profiles, winutil
from .config import Config
from .detect import Detector, Timings
from .labels import Keeper, LabelLog, labels_folder, on_print
from .protocols import PROTOCOLS, catalogue_info, get_protocol
from .serialio import (RING_SIZE, LineSettings, Opener, PortBusy, Registry, format_hex,
                       list_serial_ports, now_ms, open_real, printable)
from .simulator import SimulatorBank
from .webui import page, remote_page

log = logging.getLogger("scale_bridge")

MAX_BODY = 64 * 1024
LOCAL_HEADER = ("X-Requested-With", "ScaleBridge")
STATUS_CACHE_S = 15


def _framing_ok(text: str) -> bool:
    return len(text) == 3 and text[0] in "5678" and text[1] in "NEOMS" and text[2] in "12"


class DetectionJob:
    def __init__(self, bridge: "Bridge", ports: list[str], thorough: bool,
                 print_wait_s: float = 0, listen_only: bool = False):
        self.id = uuid.uuid4().hex[:12]
        self.bridge = bridge
        self.ports = ports
        self.thorough = thorough
        self.cancel = threading.Event()
        self.lock = threading.Lock()
        self.log: list[dict] = []
        self.results: list[dict] = []
        self.running = True
        self.started = time.time()
        self.finished: Optional[float] = None
        self.detector = Detector(bridge.opener, log=self._add, cancelled=self.cancel.is_set,
                                 thorough=thorough, timings=bridge.detect_timings,
                                 print_wait_s=print_wait_s, listen_only=listen_only)
        self.print_wait_s = print_wait_s
        self.listen_only = listen_only
        self.thread = threading.Thread(target=self._run, name="detect", daemon=True)

    def _add(self, code: str, **details: Any) -> None:
        with self.lock:
            self.log.append({"t": round(time.time() - self.started, 2), "code": code, **details})
        if code in ("found", "not_found", "open_failed"):
            log.info("detect %s %s", code, details)

    def _run(self) -> None:
        registry = self.bridge.registry
        registry.reserve(self.ports)
        try:
            for port in self.ports:
                if self.cancel.is_set():
                    break
                result = self.detector.run_port(port)
                with self.lock:
                    self.results.append(result)
                    self.detector.steps_done = 0
            self._add("done", found=sum(1 for r in self.results if r.get("found")),
                      cancelled=self.cancel.is_set())
        except Exception as e:                                  # noqa: BLE001
            log.exception("auto-detection failed")
            self._add("error", error=str(e))
        finally:
            registry.unreserve(self.ports)
            self.running = False
            self.finished = time.time()

    def start(self) -> None:
        self.thread.start()

    def status(self, since: int = 0) -> dict:
        with self.lock:
            if self.running:
                current = min(self.detector.progress, 0.99)
                progress = min(0.99, (len(self.results) + current) / max(1, len(self.ports)))
            else:
                progress = 1.0
            return {"id": self.id, "running": self.running, "ports": self.ports,
                    "thorough": self.thorough, "print_wait_s": self.print_wait_s,
                    "listen_only": self.listen_only, "progress": round(progress, 3),
                    "log": self.log[since:], "log_size": len(self.log),
                    "results": list(self.results),
                    "elapsed_s": round((self.finished or time.time()) - self.started, 1)}


class Bridge:
    """Everything the handlers share."""

    def __init__(self, config: Config, simulate: str = ""):
        self.config = config
        self.simulator = SimulatorBank(simulate) if simulate else None
        self.opener: Opener = self.simulator.opener(open_real) if self.simulator else open_real
        self.registry = Registry(self.opener)
        self.job: Optional[DetectionJob] = None
        self.job_lock = threading.Lock()
        self._status_cache: dict[str, tuple[float, dict]] = {}
        self.started = time.time()
        self.listen_port = config.listen_port
        self.detect_timings: Optional[Timings] = None
        # Print-only scales: keep their ports open and log every label.
        self.labels = LabelLog(labels_folder(config.path))
        self.keeper = Keeper(self.registry, config.profiles, self.labels)
        self.keeper.start()

    # -- ports and status --------------------------------------------------
    def ports(self) -> list[dict]:
        ports = list_serial_ports()
        if self.simulator:
            ports += self.simulator.ports()
        return ports

    def cached_status(self, key: str, fn, fresh: bool = False) -> dict:
        now = time.time()
        hit = self._status_cache.get(key)
        if hit and not fresh and now - hit[0] < STATUS_CACHE_S:
            return hit[1]
        value = fn()
        self._status_cache[key] = (now, value)
        return value

    def forget_status(self) -> None:
        self._status_cache.clear()

    # -- reading -----------------------------------------------------------
    def read_raw(self, body: dict) -> dict:
        """POST /read: the frames as they arrived (SyncPulse Serial Bridge 1.x contract)."""
        settings = LineSettings.from_dicts(body.get("serial") or {}, body.get("exchange") or {})
        wait_ms = min(max(int(body.get("wait_ms") or 2500), 0), 10000)
        max_age_ms = min(max(int(body.get("max_age_ms") or 1500), 50), 60000)
        count = min(max(int(body.get("frames") or 5), 0), RING_SIZE)
        worker = self.registry.worker_for(settings)
        worker.wait_fresh(max_age_ms, wait_ms)
        worker.touch()
        return worker.snapshot(count)

    def weight(self, profile: dict, max_age_ms: int = 1500, wait_ms: int = 2500) -> dict:
        worker = self.registry.worker_for(profiles.line_settings(profile))
        result = profiles.wait_for_reading(profile, worker, max_age_ms, wait_ms, now_ms)
        worker.touch()
        return result

    def label_list(self, query: dict) -> dict:
        name = str(query.get("profile") or "").strip() or None
        if name and self.config.profile(name) is None:
            raise LookupError(f"no profile named {name!r}")
        if name:
            name = self.config.profile(name)["name"]
        after = int(query.get("after") or 0)
        limit = min(max(int(query.get("limit") or 100), 1), 500)
        records = self.labels.list(name, after, limit)
        return {"ok": True, "labels": records, "last_seq": self.labels.seq,
                "listening": [p["name"] for p in self.config.profiles() if on_print(p)]}

    def resolve_profile(self, query: dict) -> dict:
        """A saved profile by name, or one built from the request."""
        name = str(query.get("profile") or "").strip()
        if name:
            profile = self.config.profile(name)
            if profile is None:
                raise LookupError(f"no profile named {name!r}")
            return profile
        if isinstance(query.get("serial"), dict):
            return profiles.validate({"name": "request", **query})
        port = str(query.get("port") or "").strip()
        protocol = str(query.get("protocol") or "").strip()
        if not port or not protocol:
            raise ValueError("give ?profile=NAME, or ?port=COMx&protocol=ID")
        serial_cfg: dict[str, Any] = {}
        if query.get("baud"):
            serial_cfg["baudrate"] = int(query["baud"])
        framing = str(query.get("framing") or "").upper()
        if framing:
            if not _framing_ok(framing):
                raise ValueError(f"invalid framing: {framing!r} (e.g. 8N1, 7E1)")
            serial_cfg.update(bytesize=int(framing[0]), parity=framing[1], stopbits=int(framing[2]))
        exchange = {}
        if query.get("request_hex") is not None:
            exchange = {"request_hex": str(query["request_hex"]),
                        "poll_interval_ms": int(query.get("poll_ms") or PROTOCOLS.get(protocol, PROTOCOLS["ascii_generic"]).default_poll_ms)}
        profile = profiles.ad_hoc(port, protocol, serial_cfg, exchange or None)
        if query.get("unit"):
            profile["unit"] = str(query["unit"])
        return profile

    def monitor(self, query: dict) -> dict:
        port = str(query.get("port") or "")
        framing = str(query.get("framing") or "8N1").upper()
        if not _framing_ok(framing):
            raise ValueError(f"invalid framing: {framing!r}")
        serial_cfg = {"port": port, "baudrate": int(query.get("baud") or 9600),
                      "bytesize": int(framing[0]), "parity": framing[1], "stopbits": int(framing[2])}
        exchange = {"request_hex": str(query.get("request_hex") or ""),
                    "after_ack_hex": str(query.get("after_ack_hex") or ""),
                    "poll_interval_ms": int(query.get("poll_ms") or 500)}
        settings = LineSettings.from_dicts(serial_cfg, exchange)
        worker = self.registry.worker_for(settings)
        worker.wait_fresh(1500, 1500)
        chunks = worker.recent(24)
        joined = b"".join(d for _, d in chunks)
        guesses = []
        for pid, proto in PROTOCOLS.items():
            if pid.startswith("custom"):
                continue
            found = [r for r in proto.readings(joined) if r.value is not None]
            if found:
                last = found[-1]
                guesses.append({"protocol": pid, "name": proto.name, "count": len(found),
                                "value": last.value, "unit": last.unit, "stable": last.stable,
                                "specificity": proto.specificity})
        guesses.sort(key=lambda g: (-g["specificity"], -g["count"]))
        now = now_ms()
        return {"ok": worker.is_open, "error": None if worker.is_open else worker.last_error,
                "settings": settings.describe(), "stats": dict(worker.stats),
                "frames": [{"age_ms": now - t, "hex": format_hex(d), "text": printable(d)}
                           for t, d in chunks[-16:]],
                "guesses": guesses}

    # -- auto-detection ----------------------------------------------------
    def start_detection(self, ports: Optional[list[str]], thorough: bool, bluetooth: bool,
                        print_wait_s: float = 0, listen_only: bool = False) -> DetectionJob:
        with self.job_lock:
            if self.job and self.job.running:
                raise PortBusy("auto-detection is already running")
            available = self.ports()
            if ports:
                names = {p["device"].upper(): p["device"] for p in available}
                chosen = []
                for p in ports:
                    key = str(p).upper()
                    if key not in names:
                        raise ValueError(f"no such port: {p}")
                    chosen.append(names[key])
            else:
                chosen = [p["device"] for p in available if bluetooth or p.get("kind") != "bluetooth"]
            if not chosen:
                raise ValueError("no COM ports to search — is the USB-serial adapter plugged in "
                                 "and its driver installed?")
            self.job = DetectionJob(self, chosen, thorough, min(max(float(print_wait_s or 0), 0), 300),
                                    listen_only)
            self.job.start()
            return self.job

    def state(self, fresh: bool = False) -> dict:
        port = self.listen_port
        return {
            "ok": True,
            "about": ABOUT,
            "service": SERVICE_ID,
            "host": socket.gethostname(),
            "addresses": winutil.lan_addresses(),
            "listen_port": port,
            "token": self.config.token,
            "config_path": self.config.path,
            "allowed_clients": self.config.allowed_clients,
            "simulate": bool(self.simulator),
            "is_admin": winutil.is_admin(),
            "is_windows": winutil.is_windows(),
            "firewall": self.cached_status("firewall", lambda: winutil.firewall_status(port), fresh),
            "autostart": self.cached_status("autostart", winutil.autostart_status, fresh),
            "profiles": self.config.profiles(),
            "active_ports": self.registry.active_ports(),
            "uptime_s": int(time.time() - self.started),
        }


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second program take the same port;
    # exclusive use makes a second copy of the bridge fail cleanly instead.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    server_version = f"{SERVICE_ID}/{__version__}"
    bridge: Bridge
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        log.debug("%s %s", self.client_address[0], fmt % args)

    # -- responses ---------------------------------------------------------
    def _headers(self, code: int, content_type: str, length: int) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")

    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self._headers(code, "application/json; charset=utf-8", len(data))
        self.end_headers()
        self.wfile.write(data)

    def _send_html(self, html: str, code: int = 200) -> None:
        data = html.encode("utf-8")
        self._headers(code, "text/html; charset=utf-8", len(data))
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                         "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code: int, message: str) -> None:
        self._send(code, {"ok": False, "error": message})

    # -- who is asking -----------------------------------------------------
    @property
    def _client(self) -> str:
        return self.client_address[0]

    def _is_loopback(self) -> bool:
        ip = self._client
        return ip.startswith("127.") or ip in ("::1", "::ffff:127.0.0.1")

    def _host_is_local(self) -> bool:
        host = (self.headers.get("Host") or "").strip().lower()
        if host.startswith("["):
            name = host[1:host.find("]")] if "]" in host else host
        else:
            name = host.split(":")[0]
        return name in ("127.0.0.1", "localhost", "::1")

    def _local_page_ok(self) -> bool:
        return self._is_loopback() and self._host_is_local()

    def _local_api_ok(self) -> bool:
        if not self._local_page_ok() or self.headers.get(LOCAL_HEADER[0]) != LOCAL_HEADER[1]:
            self._error(403, "this part of the bridge is only for the page on this PC")
            return False
        return True

    def _client_allowed(self) -> bool:
        allowed = self.bridge.config.allowed_clients
        if allowed and not self._is_loopback() and self._client not in allowed:
            self._error(403, f"client {self._client} is not in allowed_clients")
            return False
        return True

    def _authorized(self) -> bool:
        given = (self.headers.get("X-Bridge-Token") or "").encode()
        expected = self.bridge.config.token.encode()
        if not expected or not hmac.compare_digest(given, expected):
            self._error(401, "invalid or missing X-Bridge-Token")
            return False
        return True

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("body too large")
        raw = self.rfile.read(length) if length else b""
        body = json.loads(raw or b"{}")
        if not isinstance(body, dict):
            raise ValueError("body must be a JSON object")
        return body

    def _query(self) -> tuple[str, dict]:
        parts = urlsplit(self.path)
        query = {k: v[-1] for k, v in parse_qs(parts.query).items()}
        return parts.path.rstrip("/") or "/", query

    # -- dispatch ----------------------------------------------------------
    def do_GET(self) -> None:                                   # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:                                  # noqa: N802
        self._dispatch("POST")

    def do_DELETE(self) -> None:                                # noqa: N802
        self._dispatch("DELETE")

    def _dispatch(self, method: str) -> None:
        path, query = self._query()
        try:
            if path.startswith("/api/"):
                if self._local_api_ok():
                    self._local_api(method, path, query)
                return
            if path == "/" and method == "GET":
                if self._local_page_ok():
                    self._send_html(page())
                else:
                    self._send_html(remote_page(self.bridge.listen_port))
                return
            if path == "/favicon.ico":
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if not self._client_allowed():
                return
            self._network_api(method, path, query)
        except PortBusy as e:
            self._error(409, str(e))
        except LookupError as e:
            self._error(404, str(e))
        except (ValueError, TypeError, KeyError) as e:
            self._error(400, str(e))
        except Exception as e:                                  # noqa: BLE001
            log.exception("%s %s failed", method, path)
            self._error(500, f"{e.__class__.__name__}: {e}")

    def _network_api(self, method: str, path: str, query: dict) -> None:
        b = self.bridge
        if path == "/health" and method == "GET":
            self._send(200, {"ok": True, "service": SERVICE_ID, "product": PRODUCT,
                             "version": __version__, "host": socket.gethostname(),
                             "simulate": bool(b.simulator), "author": ABOUT["author"],
                             "website": ABOUT["website"], "repository": ABOUT["repository"],
                             "capabilities": ["read", "ports", "weight", "profiles", "detect"]})
            return
        if not self._authorized():
            return
        if path == "/ports" and method == "GET":
            self._send(200, {"ok": True, "ports": b.ports()})
        elif path == "/read" and method == "POST":
            self._send(200, b.read_raw(self._body()))
        elif path == "/profiles" and method == "GET":
            self._send(200, {"ok": True, "profiles": b.config.profiles()})
        elif path == "/labels" and method == "GET":
            self._send(200, b.label_list(query))
        elif path == "/weight" and method in ("GET", "POST"):
            body = query if method == "GET" else {**query, **self._body()}
            profile = b.resolve_profile(body)
            self._send(200, b.weight(profile, *self._timing(body)))
        else:
            self._error(404, "not found")

    @staticmethod
    def _timing(q: dict) -> tuple[int, int]:
        max_age = min(max(int(q.get("max_age_ms") or 1500), 50), 60000)
        wait = min(max(int(q.get("wait_ms") or 2500), 0), 10000)
        return max_age, wait

    def _local_api(self, method: str, path: str, query: dict) -> None:
        b = self.bridge
        if method == "GET":
            if path == "/api/state":
                self._send(200, b.state(fresh=query.get("fresh") == "1"))
            elif path == "/api/ports":
                self._send(200, {"ok": True, "ports": b.ports()})
            elif path == "/api/protocols":
                self._send(200, {"ok": True, "protocols": catalogue_info()})
            elif path == "/api/weight":
                profile = b.resolve_profile(query)
                self._send(200, b.weight(profile, *self._timing(query)))
            elif path == "/api/labels":
                self._send(200, b.label_list(query))
            elif path == "/api/monitor":
                self._send(200, b.monitor(query))
            elif path == "/api/detect":
                job = b.job
                since = int(query.get("since") or 0)
                self._send(200, {"ok": True, "job": job.status(since) if job else None})
            else:
                self._error(404, "not found")
            return

        if method == "DELETE":
            if path.startswith("/api/profiles/"):
                name = unquote(path[len("/api/profiles/"):])
                if not b.config.delete_profile(name):
                    raise LookupError(f"no profile named {name!r}")
                self._send(200, {"ok": True, "profiles": b.config.profiles()})
            else:
                self._error(404, "not found")
            return

        body = self._body()
        if path == "/api/detect":
            job = b.start_detection(body.get("ports") or None, bool(body.get("thorough")),
                                    bool(body.get("bluetooth")), body.get("print_wait_s") or 0,
                                    bool(body.get("listen_only")))
            self._send(200, {"ok": True, "job": job.status()})
        elif path == "/api/detect/cancel":
            if b.job and b.job.running:
                b.job.cancel.set()
            self._send(200, {"ok": True})
        elif path == "/api/profiles":
            if isinstance(body.get("detection"), dict):
                profile = profiles.from_detection(body["detection"], str(body.get("name") or ""),
                                                  str(body.get("label") or ""))
                if body.get("unit"):
                    profile["unit"] = profiles.norm_unit(body["unit"])
            else:
                profile = body
            saved = b.config.save_profile(profile)
            b.registry.release(saved["port"])
            b.keeper.tick()
            self._send(200, {"ok": True, "profile": saved, "profiles": b.config.profiles()})
        elif path == "/api/token":
            self._send(200, {"ok": True, "token": b.config.rotate_token()})
        elif path == "/api/allowed":
            clients = body.get("clients") or []
            if not isinstance(clients, list):
                raise ValueError("clients must be a list")
            b.config.set_allowed_clients(clients)
            self._send(200, {"ok": True, "allowed_clients": b.config.allowed_clients})
        elif path == "/api/firewall":
            remote = str(body.get("remote_ip") or "").strip() or None
            if remote:
                import ipaddress
                ipaddress.ip_address(remote)
            result = (winutil.firewall_close() if body.get("remove")
                      else winutil.firewall_open(b.listen_port, remote))
            b.forget_status()
            self._send(200, {**result, "state": b.state(fresh=True)})
        elif path == "/api/autostart":
            result = (winutil.autostart_enable(b.config.path) if body.get("enable")
                      else winutil.autostart_disable())
            b.forget_status()
            self._send(200, {**result, "state": b.state(fresh=True)})
        else:
            self._error(404, "not found")


def make_server(bridge: Bridge, host: str, port: int) -> Server:
    Handler.bridge = bridge
    bridge.listen_port = port
    return Server((host, port), Handler)
