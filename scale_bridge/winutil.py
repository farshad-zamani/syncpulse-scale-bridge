# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
Windows chores the bridge can do by itself, each behind one button:

* open the firewall for the bridge port (so other machines can reach it),
* start the bridge with Windows, before anyone logs in (a scheduled task that
  runs as SYSTEM, never stops after 72 hours, and restarts if it fails).

Both need administrator rights; Windows shows its usual UAC prompt.
Everything returns plain dictionaries for the user interface.
"""
from __future__ import annotations

import ctypes
import logging
import os
import socket
import subprocess
import sys
import tempfile
import webbrowser
from typing import Optional

from . import PRODUCT

log = logging.getLogger("scale_bridge")

RULE_NAME = PRODUCT
TASK_NAME = PRODUCT
CREATE_NO_WINDOW = 0x08000000
ERROR_CANCELLED = 1223


def is_windows() -> bool:
    return sys.platform == "win32"


def is_admin() -> bool:
    if not is_windows():
        return os.geteuid() == 0 if hasattr(os, "geteuid") else False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:                                           # noqa: BLE001
        return False


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def program_command(extra: str) -> tuple[str, str, str]:
    """(executable, arguments, working directory) that start this program again."""
    if is_frozen():
        exe = os.path.abspath(sys.executable)
        return exe, extra, os.path.dirname(exe)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.abspath(sys.executable), f"-m scale_bridge {extra}", root


def _run(args: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, timeout=timeout,
                          creationflags=CREATE_NO_WINDOW if is_windows() else 0)


# ---------------------------------------------------------------------------
# Elevation
# ---------------------------------------------------------------------------

def run_elevated(exe: str, params: str, timeout: float = 120) -> dict:
    """Run a command as administrator (UAC prompt) and wait for it."""
    if not is_windows():
        return {"ok": False, "error": "Windows only"}
    if is_admin():
        try:
            proc = subprocess.run(f'"{exe}" {params}', capture_output=True, timeout=timeout,
                                  creationflags=CREATE_NO_WINDOW)
            return {"ok": proc.returncode == 0, "code": proc.returncode}
        except (OSError, subprocess.SubprocessError) as e:
            return {"ok": False, "error": str(e)}

    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                    ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                    ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                    ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
                    ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
                    ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                    ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SEE_MASK_NO_CONSOLE = 0x00008000
    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS | SEE_MASK_NO_CONSOLE
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.nShow = 0                                              # SW_HIDE
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        err = ctypes.GetLastError()
        if err == ERROR_CANCELLED:
            return {"ok": False, "cancelled": True, "error": "cancelled at the Windows prompt"}
        return {"ok": False, "error": f"Windows error {err}"}
    try:
        kernel32.WaitForSingleObject(info.hProcess, int(timeout * 1000))
        code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(code))
        return {"ok": code.value == 0, "code": code.value}
    finally:
        kernel32.CloseHandle(info.hProcess)


# ---------------------------------------------------------------------------
# Firewall
# ---------------------------------------------------------------------------

def firewall_status(port: int) -> dict:
    if not is_windows():
        return {"supported": False}
    try:
        proc = _run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE_NAME}"])
    except (OSError, subprocess.SubprocessError) as e:
        return {"supported": True, "exists": False, "error": str(e)}
    exists = proc.returncode == 0
    return {"supported": True, "exists": exists,
            "port_ok": exists and str(port).encode() in proc.stdout, "rule": RULE_NAME}


def firewall_open(port: int, remote_ip: Optional[str] = None) -> dict:
    """Allow inbound TCP `port` on every network profile (optionally from one address only).

    When Windows asked "allow access?" the first time the program listened and
    somebody clicked Cancel, Windows added BLOCK rules for the program, and a
    block rule beats any allow rule — so those are removed as well.
    """
    if not is_windows():
        return {"ok": False, "error": "Windows only"}
    port = int(port)
    remote = f" remoteip={remote_ip}" if remote_ip else ""
    steps = [f'netsh advfirewall firewall delete rule name="{RULE_NAME}" >nul 2>&1']
    if is_frozen():
        steps.append(f'netsh advfirewall firewall delete rule name=all program="{sys.executable}" >nul 2>&1')
    steps.append(f'netsh advfirewall firewall add rule name="{RULE_NAME}" dir=in action=allow '
                 f'protocol=TCP localport={port} profile=any{remote} '
                 f'description="{PRODUCT}: lets other machines read the scales on this PC"')
    result = run_elevated(os.environ.get("COMSPEC", "cmd.exe"), "/c " + " & ".join(steps))
    result["status"] = firewall_status(port)
    result["ok"] = bool(result["status"].get("port_ok"))
    return result


def firewall_close() -> dict:
    if not is_windows():
        return {"ok": False, "error": "Windows only"}
    return run_elevated("netsh", f'advfirewall firewall delete rule name="{RULE_NAME}"')


# ---------------------------------------------------------------------------
# Start with Windows
# ---------------------------------------------------------------------------

def _xml_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def task_xml(exe: str, arguments: str, workdir: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{_xml_escape(PRODUCT)}: serves the scales on this PC to the network.</Description>
  </RegistrationInfo>
  <Triggers>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT20S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-18</UserId>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>6</Priority>
    <RestartOnFailure>
      <Interval>PT1M</Interval>
      <Count>999</Count>
    </RestartOnFailure>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{_xml_escape(exe)}</Command>
      <Arguments>{_xml_escape(arguments)}</Arguments>
      <WorkingDirectory>{_xml_escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def autostart_status() -> dict:
    if not is_windows():
        return {"supported": False}
    try:
        proc = _run(["schtasks", "/Query", "/TN", TASK_NAME, "/XML"])
    except (OSError, subprocess.SubprocessError) as e:
        return {"supported": True, "enabled": False, "error": str(e)}
    if proc.returncode != 0:
        return {"supported": True, "enabled": False, "task": TASK_NAME}
    xml = proc.stdout.decode("utf-16", errors="ignore") if proc.stdout[:2] in (b"\xff\xfe", b"\xfe\xff") \
        else proc.stdout.decode("utf-8", errors="ignore")
    exe, _, _ = program_command("")
    return {"supported": True, "enabled": True, "task": TASK_NAME,
            "this_program": exe.lower() in xml.lower()}


def autostart_enable(config_path: str) -> dict:
    if not is_windows():
        return {"ok": False, "error": "Windows only"}
    exe, arguments, workdir = program_command(f'--service --config "{config_path}"')
    fd, xml_path = tempfile.mkstemp(prefix="scale-bridge-task-", suffix=".xml")
    with os.fdopen(fd, "wb") as f:
        f.write(task_xml(exe, arguments, workdir).encode("utf-16"))
    try:
        result = run_elevated("schtasks", f'/Create /TN "{TASK_NAME}" /XML "{xml_path}" /F')
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    result["status"] = autostart_status()
    result["ok"] = bool(result["status"].get("enabled"))
    return result


def autostart_disable() -> dict:
    if not is_windows():
        return {"ok": False, "error": "Windows only"}
    result = run_elevated("schtasks", f'/Delete /TN "{TASK_NAME}" /F')
    result["status"] = autostart_status()
    result["ok"] = not result["status"].get("enabled")
    return result


# ---------------------------------------------------------------------------
# Network and desktop
# ---------------------------------------------------------------------------

def lan_addresses() -> list[str]:
    found = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            found.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                found.add(ip)
    except OSError:
        pass
    return sorted(found)


def open_browser(url: str) -> None:
    try:
        webbrowser.open(url, new=1)
    except Exception:                                           # noqa: BLE001
        log.info("open %s in a browser", url)
