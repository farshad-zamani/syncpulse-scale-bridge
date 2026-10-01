# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Command line. Without a command the bridge starts and its page opens in the
browser — that is what a double-click on the program does.

    SyncPulseScaleBridge                       run, open http://127.0.0.1:8765/
    SyncPulseScaleBridge ports                 list COM ports
    SyncPulseScaleBridge detect [--port COM7] [--thorough] [--save NAME]
    SyncPulseScaleBridge monitor --port COM7 [--baud 9600 --framing 8N1 --request "SI\\r\\n" hex]
    SyncPulseScaleBridge weight --profile NAME | --port COM7 --protocol mt_sics
    SyncPulseScaleBridge token [--new]
    SyncPulseScaleBridge firewall [--remove] [--remote-ip 192.168.1.10]
    SyncPulseScaleBridge autostart [--disable]
    SyncPulseScaleBridge about

Common options: --config FILE, --simulate SPEC (e.g. mahak_mds,toledo_cont:4800:7E1),
--verbose; for running: --listen-host, --listen-port, --no-browser, --service.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from typing import Optional

from . import ABOUT, PRODUCT, SERVICE_ID, __version__, profiles, winutil
from .config import Config
from .detect import Detector
from .protocols import PROTOCOLS, catalogue_info
from .serialio import LineSettings, Registry, format_hex, list_serial_ports, now_ms, open_real, parse_hex, printable
from .simulator import SimulatorBank

log = logging.getLogger("scale_bridge")

LOG_TEXT = {
    "port_start": "Searching {port} ...",
    "listen": "  listening at {baud} {framing}",
    "heard": "  heard {bytes} bytes at {baud} ({readable_pct}% readable)",
    "seven_bit": "  7 data bits with parity? listening again as 7E1/7O1",
    "reply": "  reply to {protocol}: {text}",
    "found": "  FOUND {protocol} at {baud} {framing}: {value} {unit}",
    "not_found": "  nothing recognised on {port}",
    "open_failed": "  cannot open {port}: {error}",
}


def say(text: str = "") -> None:
    try:
        print(text, flush=True)
    except Exception:                                           # noqa: BLE001
        try:
            sys.stdout.buffer.write((text + "\n").encode("ascii", "replace"))
            sys.stdout.flush()
        except Exception:                                       # noqa: BLE001
            pass


def setup_logging(directory: str, verbose: bool, quiet_console: bool = False) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handlers: list[logging.Handler] = []
    if not quiet_console and sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        handlers.append(console)
    try:
        os.makedirs(directory, exist_ok=True)
        file_handler = RotatingFileHandler(os.path.join(directory, "bridge.log"), maxBytes=1_000_000,
                                           backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        handlers.append(file_handler)
    except OSError:
        pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers or None,
                        force=True)


def _opener(args):
    if args.simulate:
        return SimulatorBank(args.simulate).opener(open_real), SimulatorBank(args.simulate)
    return open_real, None


def _ports(args) -> list[dict]:
    ports = list_serial_ports()
    if args.simulate:
        ports += SimulatorBank(args.simulate).ports()
    return ports


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_ports(args) -> int:
    ports = _ports(args)
    if not ports:
        say("No COM ports found. Plug in the USB-serial adapter and check its driver in Device Manager.")
        return 1
    for p in ports:
        chip = f"  [{p['chip']}]" if p.get("chip") else ""
        say(f"{p['device']:8} {p.get('description') or ''}{chip}  ({p.get('kind')})")
        if p.get("note"):
            say(f"         note: {p['note']}")
    return 0


def cmd_detect(args, config: Config) -> int:
    opener, _ = _opener(args)
    ports = args.ports or [p["device"] for p in _ports(args)
                           if args.bluetooth or p.get("kind") != "bluetooth"]
    if not ports:
        say("No COM ports to search.")
        return 1

    def show(code: str, **kw) -> None:
        text = LOG_TEXT.get(code)
        if text and (args.verbose or code != "listen"):
            kw.setdefault("readable_pct", round(float(kw.get("readable") or 0) * 100))
            if "protocol" in kw and kw["protocol"] in PROTOCOLS:
                kw["protocol"] = PROTOCOLS[kw["protocol"]].name
            try:
                say(text.format(**kw))
            except (KeyError, IndexError):
                say(f"  {code} {kw}")

    say(f"{PRODUCT} {__version__} - auto-detection ({'thorough' if args.thorough else 'quick'}); "
        f"read-only requests only.")
    results = Detector(opener, log=show, thorough=args.thorough).run(ports)
    say()
    found = [r for r in results if r.get("found")]
    for r in results:
        if r.get("found"):
            s = r["serial"]
            reading = r["reading"]
            say(f"{r['port']}: {r['protocol_name']}  {s['baudrate']} {s['bytesize']}{s['parity']}{s['stopbits']}"
                f"  request={r['exchange']['request_hex'] or '-'}  weight={reading['value']} {reading['unit']}"
                f"  confidence={int(r['confidence'] * 100)}%")
        else:
            unknown = r.get("unknown")
            extra = f"  (readable data at {unknown['baud']} {unknown['framing']}: {unknown['sample_text'][:60]})" \
                if unknown else ""
            say(f"{r['port']}: no scale recognised{extra}{'  - ' + r['error'] if r.get('error') else ''}")
    if args.save and found:
        for i, r in enumerate(found):
            name = args.save if len(found) == 1 else f"{args.save}-{profiles.slug(r['port'])}"
            saved = config.save_profile(profiles.from_detection(r, name))
            say(f"saved profile '{saved['name']}' in {config.path}")
    if args.json:
        say(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if found else 1


def cmd_monitor(args) -> int:
    opener, _ = _opener(args)
    framing = args.framing.upper()
    request = parse_hex(args.request or "")
    settings = LineSettings(args.port).with_line(args.baud, framing)
    say(f"{settings.port} {settings.baudrate} {settings.framing}, "
        f"{'request ' + format_hex(request) + ' every ' + str(args.poll) + ' ms' if request else 'listening'}"
        f" for {args.seconds} s (Ctrl+C stops)")
    ser = opener(settings)
    collected = bytearray()
    try:
        end = time.monotonic() + args.seconds
        next_request = 0.0
        buf, last = bytearray(), time.monotonic()
        while time.monotonic() < end:
            now = time.monotonic()
            if request and now >= next_request:
                ser.write(request)
                next_request = now + args.poll / 1000
            waiting = ser.in_waiting
            chunk = ser.read(waiting if waiting else 1)
            if chunk:
                buf += chunk
                last = time.monotonic()
                continue
            if buf and time.monotonic() - last > 0.05:
                say(f"{format_hex(bytes(buf))}   |  {printable(bytes(buf))}")
                collected += buf
                buf.clear()
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()
    say()
    readable = [(pid, p) for pid, p in PROTOCOLS.items() if not pid.startswith("custom")]
    for pid, proto in readable:
        found = [r for r in proto.readings(bytes(collected)) if r.value is not None]
        if found:
            say(f"readable as {proto.name}: {found[-1].value} {found[-1].unit} (x{len(found)})")
    return 0


def cmd_weight(args, config: Config) -> int:
    opener, _ = _opener(args)
    if args.profile:
        profile = config.profile(args.profile)
        if profile is None:
            say(f"no profile named {args.profile!r} in {config.path}")
            return 1
    elif args.port and args.protocol:
        serial_cfg = {"baudrate": args.baud}
        if args.framing:
            f = args.framing.upper()
            serial_cfg.update(bytesize=int(f[0]), parity=f[1], stopbits=int(f[2]))
        profile = profiles.ad_hoc(args.port, args.protocol, serial_cfg)
    else:
        say("give --profile NAME, or --port COMx --protocol ID")
        return 2
    registry = Registry(opener)
    try:
        worker = registry.worker_for(profiles.line_settings(profile))
        result = profiles.wait_for_reading(profile, worker, 1500, int(args.wait * 1000), now_ms)
    finally:
        registry.stop_all()
    say(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("ok") else 1


def cmd_token(args, config: Config) -> int:
    say(config.rotate_token() if args.new else config.token)
    return 0


def cmd_firewall(args, config: Config) -> int:
    result = winutil.firewall_close() if args.remove else winutil.firewall_open(config.listen_port, args.remote_ip)
    say(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def cmd_autostart(args, config: Config) -> int:
    result = winutil.autostart_disable() if args.disable else winutil.autostart_enable(config.path)
    say(json.dumps(result, indent=2))
    return 0 if result.get("ok") else 1


def cmd_about() -> int:
    for key in ("product", "version", "author", "company", "website", "github", "linkedin",
                "repository", "license"):
        say(f"{key:11} {ABOUT[key]}")
    say(f"Built for the {ABOUT['platform']} platform. {ABOUT['copyright']}")
    return 0


def cmd_protocols() -> int:
    for p in catalogue_info():
        tested = "  [field-tested]" if p["field_tested"] else ""
        say(f"{p['id']:16} {p['kind']:10} {p['request_hex'] or '-':14} {p['name']}{tested}")
    return 0


# ---------------------------------------------------------------------------
# Running the bridge
# ---------------------------------------------------------------------------

def _running_copy(port: int) -> Optional[dict]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            body = json.loads(r.read().decode("utf-8"))
            return body if body.get("service") == SERVICE_ID else None
    except Exception:                                           # noqa: BLE001
        return None


def cmd_run(args, config: Config) -> int:
    from .server import Bridge, make_server

    host = args.listen_host or config.listen_host
    port = int(args.listen_port or config.listen_port)
    url = f"http://127.0.0.1:{port}/"
    open_page = not (args.no_browser or args.service)
    bridge = Bridge(config, simulate=args.simulate or "")
    try:
        httpd = make_server(bridge, host, port)
    except OSError as e:
        other = _running_copy(port)
        if other:
            say(f"{PRODUCT} is already running on this PC (version {other.get('version')}).")
            if open_page:
                say(f"Opening {url}")
                winutil.open_browser(url)
            return 0
        log.error("cannot listen on %s:%d: %s", host, port, e)
        say(f"Port {port} is used by another program. Close it, or start with --listen-port 8766.")
        return 1

    bar = "=" * 68
    say(bar)
    say(f" {PRODUCT} {__version__}" + ("   [SIMULATION]" if args.simulate else ""))
    say(f" {ABOUT['copyright']} - {ABOUT['website']}")
    say(f" Built for the {ABOUT['platform']} platform - {ABOUT['license']}")
    say(bar)
    say(f" Control page (this PC) : {url}")
    for ip in winutil.lan_addresses() or ["<this PC's IP address>"]:
        say(f" Bridge address         : {ip}   port {port}")
    say(f" Access key             : {config.token}")
    say(f" Settings               : {config.path}")
    say(bar)
    say(" Keep this window open while the scales are in use; closing it stops the bridge.")
    say(" To run in the background at startup, use 'Start with Windows' on the control page.")
    say(bar)
    log.info("listening on %s:%d", host, port)
    if open_page:
        winutil.open_browser(url)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        bridge.registry.stop_all()
    return 0


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument("--config", help="settings file (default: bridge.json beside the program)")
    common.add_argument("--simulate", metavar="SPEC",
                        help="add simulated scales on COM90.. e.g. 'mahak_mds,toledo_cont:4800:7E1'")
    common.add_argument("--verbose", action="store_true", help="more detail in the log")

    ap = argparse.ArgumentParser(
        prog="SyncPulseScaleBridge",
        description=f"{PRODUCT} {__version__} - finds RS-232 scales, reads them and serves the weight "
                    f"on the network. Built for the {ABOUT['platform']} platform.",
        epilog=f"{ABOUT['copyright']} - {ABOUT['website']} - {ABOUT['repository']}")
    ap.add_argument("--version", action="version", version=f"{PRODUCT} {__version__}")
    ap.add_argument("--config", default=None)
    ap.add_argument("--simulate", default="", metavar="SPEC")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--listen-host", help="address to listen on (default 0.0.0.0)")
    ap.add_argument("--listen-port", type=int, help="port to listen on (default 8765)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the control page")
    ap.add_argument("--service", action="store_true", help="background mode (used by 'Start with Windows')")
    sub = ap.add_subparsers(dest="command", metavar="command")

    sub.add_parser("run", parents=[common], help="run the bridge (the default)")
    sub.add_parser("ports", parents=[common], help="list COM ports")
    d = sub.add_parser("detect", parents=[common], help="find the scale automatically")
    d.add_argument("--port", dest="ports", action="append", help="only this port (repeatable)")
    d.add_argument("--thorough", action="store_true", help="more speeds and framings (slower)")
    d.add_argument("--bluetooth", action="store_true", help="also search Bluetooth serial ports")
    d.add_argument("--save", metavar="NAME", help="save what is found as a profile")
    d.add_argument("--json", action="store_true", help="print the full results as JSON")
    m = sub.add_parser("monitor", parents=[common], help="show the raw bytes on a port")
    m.add_argument("--port", required=True)
    m.add_argument("--baud", type=int, default=9600)
    m.add_argument("--framing", default="8N1")
    m.add_argument("--request", default="", help="hex bytes to send, e.g. '53 49 0D 0A'")
    m.add_argument("--poll", type=int, default=500, help="request interval in ms")
    m.add_argument("--seconds", type=float, default=10)
    w = sub.add_parser("weight", parents=[common], help="read the weight once")
    w.add_argument("--profile")
    w.add_argument("--port")
    w.add_argument("--protocol", choices=sorted(PROTOCOLS))
    w.add_argument("--baud", type=int, default=9600)
    w.add_argument("--framing", default="")
    w.add_argument("--wait", type=float, default=3.0, help="seconds to wait for a reading")
    t = sub.add_parser("token", parents=[common], help="show the access key")
    t.add_argument("--new", action="store_true", help="make a new key")
    f = sub.add_parser("firewall", parents=[common], help="open the bridge port in Windows Firewall")
    f.add_argument("--remove", action="store_true")
    f.add_argument("--remote-ip", default=None, help="allow only this address")
    a = sub.add_parser("autostart", parents=[common], help="start with Windows (scheduled task)")
    a.add_argument("--disable", action="store_true")
    sub.add_parser("protocols", parents=[common], help="list the protocol library")
    sub.add_parser("about", parents=[common], help="author, licence and links")
    return ap


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"
    if command == "about":
        return cmd_about()
    if command == "protocols":
        return cmd_protocols()
    if command == "ports":
        return cmd_ports(args)
    if command == "monitor":
        return cmd_monitor(args)

    config = Config(args.config)
    setup_logging(os.path.dirname(config.path), args.verbose,
                  quiet_console=command != "run" and not args.verbose)
    if command == "detect":
        return cmd_detect(args, config)
    if command == "weight":
        return cmd_weight(args, config)
    if command == "token":
        return cmd_token(args, config)
    if command == "firewall":
        return cmd_firewall(args, config)
    if command == "autostart":
        return cmd_autostart(args, config)
    return cmd_run(args, config)
