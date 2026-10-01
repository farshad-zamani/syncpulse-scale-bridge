# SPDX-License-Identifier: GPL-3.0-or-later
"""Auto-detection against simulated scales that only understand their own settings."""
import time

import pytest

from scale_bridge.detect import Detector, Timings, readability
from scale_bridge.simulator import SimulatorBank

FAST = Timings(passive_s=0.5, probe_s=0.15, confirm_s=0.4, drain_s=0.02)


class Silent:
    """A port with nothing connected."""
    in_waiting = 0

    def __init__(self, settings):
        self.settings = settings

    def read(self, n=1):
        time.sleep(0.01)
        return b""

    def write(self, data):
        return len(data)

    def close(self):
        pass


class Chatter(Silent):
    """Readable text without any weight in it."""

    def read(self, n=1):
        time.sleep(0.01)
        return b"HELLO WORLD\r\n" if self.settings.baudrate == 9600 else b""

    @property
    def in_waiting(self):
        return 0


def detect(spec, port="COM90", thorough=False):
    bank = SimulatorBank(spec)
    events = []
    result = Detector(bank.opener(), log=lambda code, **kw: events.append(code), thorough=thorough,
                      timings=FAST).run_port(port)
    return result, events


@pytest.mark.parametrize("spec,protocol,baud,framing,mode", [
    ("mahak_mds", "mahak_mds", 9600, "8N1", "poll"),
    ("toledo_cont:4800:7E1", "toledo_cont", 4800, "7E1", "continuous"),
    ("xk3190_tf0:2400", "xk3190_tf0", 2400, "8N1", "continuous"),
    ("xk3190_reversed:1200", "xk3190_reversed", 1200, "8N1", "continuous"),
    ("mt_sics", "mt_sics", 9600, "8N1", "poll"),
    ("and_std:19200", "and_std", 19200, "8N1", "poll"),
    ("sma:9600:7E1", "sma", 9600, "7E1", "poll"),
    ("sartorius:1200:7E1", "sartorius", 1200, "7E1", "poll"),
    ("cas_enq", "cas_enq", 9600, "8N1", "poll"),
])
def test_finds_protocol_speed_and_framing(spec, protocol, baud, framing, mode):
    result, events = detect(spec)
    assert result["found"], events
    assert result["protocol"] == protocol
    assert result["serial"]["baudrate"] == baud
    s = result["serial"]
    assert f"{s['bytesize']}{s['parity']}{s['stopbits']}" == framing
    assert result["mode"] == mode
    assert 0 < result["confidence"] <= 0.99
    assert events[0] == "port_start" and "found" in events


def test_thorough_search_reaches_7o1():
    result, _ = detect("ohaus:9600:7O1", thorough=True)
    assert result["found"] and result["protocol"] == "ohaus"
    assert result["serial"]["parity"] == "O"


def test_nothing_connected():
    detector = Detector(lambda s: Silent(s), timings=FAST)
    result = detector.run_port("COM5")
    assert result["found"] is False and result["unknown"] is None


def test_unknown_readable_data_is_reported():
    detector = Detector(lambda s: Chatter(s), timings=FAST)
    result = detector.run_port("COM5")
    assert result["found"] is False
    assert result["unknown"]["baud"] == 9600
    assert "HELLO" in result["unknown"]["sample_text"]


def test_cancel_stops_quickly():
    detector = Detector(lambda s: Silent(s), cancelled=lambda: True, timings=FAST)
    started = time.monotonic()
    result = detector.run_port("COM5")
    assert time.monotonic() - started < 0.5
    assert result["found"] is False and result["cancelled"] is True


def test_open_failure_is_reported():
    def refuse(settings):
        raise OSError("Access is denied")
    result = Detector(refuse, timings=FAST).run_port("COM5")
    assert result["found"] is False and "Access is denied" in result["error"]


def test_readability():
    assert readability(b"ST,+0.55 kg\r\n") == 1.0
    assert readability(bytes([0xD3, 0xD4])) == 0.0
    assert readability(bytes([0xD3, 0xD4]), mask7=True) == 1.0
