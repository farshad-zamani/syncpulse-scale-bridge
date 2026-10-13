# SPDX-License-Identifier: GPL-3.0-or-later
"""Indicators that print labels: the PTC400 capture, other label languages, the label log."""
import json
import os
import time

import pytest

from scale_bridge import profiles
from scale_bridge.detect import Detector, Timings
from scale_bridge.labels import LabelLog
from scale_bridge.protocols import PROTOCOLS
from scale_bridge.simulator import SimulatorBank

HERE = os.path.dirname(os.path.abspath(__file__))
FAST = Timings(passive_s=0.4, probe_s=0.1, confirm_s=0.3, drain_s=0.02)


def capture() -> list[bytes]:
    with open(os.path.join(HERE, "captures", "ptc400_tspl_labels.hex"), encoding="ascii") as f:
        return [bytes.fromhex(line) for line in f if line.strip()]


def test_ptc400_capture_all_labels():
    # Recorded from a PTC400 indicator (TSPL to a TSC label printer), a 1.4 kg
    # test weight moved around the platform after three other weighings.
    readings = PROTOCOLS["label_print"].readings(b"".join(capture()))
    assert [r.value for r in readings] == [102.3, 141.8, 141.2, 1.4, 1.4, 1.35, 1.3, 1.25, 0.95,
                                           1.2, 1.25, 1.15]
    first = readings[0]
    assert first.unit == "kg" and first.stable is True
    assert first.fields["Order.Co"] == "222" and first.fields["SHIFT"] == "2"
    assert first.fields["date"] == "1405/07/19" and first.fields["time"] == "16:39"
    assert first.fields["Thickness"] == "0.0" and first.fields["No"] == "6"
    assert readings[2].fields["Thickness"] == "3.3"


def test_label_split_over_two_chunks_is_read_once():
    label = capture()[0]
    chunks = [(1000, label[:200]), (1020, label[200:])]
    timed = profiles.timed_readings("label_print", None, chunks)
    assert len(timed) == 1 and timed[0].t_ms == 1020 and timed[0].reading.value == 102.3


@pytest.mark.parametrize("label,value,unit", [
    (b'^XA^FO50,50^A0N,40,40^FDNet: 12.34 kg^FS^FO50,120^FDLOT 7^FS^XZ', 12.34, "kg"),
    (b'N\r\nA50,0,0,4,1,1,N,"Weight"\r\nA50,40,0,4,1,1,N,"2.500"\r\nA200,40,0,4,1,1,N,"kg"\r\nP1\r\n',
     2.5, "kg"),
    (b'CLS\r\nTEXT 10,10,"3",0,1,1,"GROSS 15.6 kg"\r\nPRINT 1,1\r\n', 15.6, "kg"),
])
def test_other_label_languages(label, value, unit):
    r = PROTOCOLS["label_print"].readings(label)[-1]
    assert (r.value, r.unit) == (value, unit)


def test_label_without_weight_is_ignored():
    assert PROTOCOLS["label_print"].readings(b'CLS\r\nTEXT 1,1,"3",0,1,1,"Hello"\r\nPRINT 1\r\n') == []


@pytest.mark.parametrize("spec,baud,parity,wrong", [
    ("label_print", 9600, "N", 0), ("label_print:4800", 4800, "N", 2), ("label_print:9600:7E1", 9600, "E", 0),
])
def test_wait_for_print_detection(spec, baud, parity, wrong):
    bank = SimulatorBank(spec)
    events = []
    detector = Detector(bank.opener(), log=lambda code, **kw: events.append(code), timings=FAST,
                        print_wait_s=5, listen_only=True)
    result = detector.run_port("COM90")
    assert result["found"] and result["protocol"] == "label_print" and result["mode"] == "print"
    assert result["serial"]["baudrate"] == baud and result["serial"]["parity"] == parity
    assert result["reading"]["fields"]["Order.Co"] == "222"
    assert events.count("print_wrong_speed") == wrong
    assert "ask" not in events                      # listen only: nothing was sent


def test_listen_only_sends_nothing():
    written = []

    class Quiet:
        in_waiting = 0

        def __init__(self, s):
            pass

        def read(self, n=1):
            time.sleep(0.01)
            return b""

        def write(self, data):
            written.append(data)
            return len(data)

        def close(self):
            pass

    result = Detector(lambda s: Quiet(s), timings=FAST, print_wait_s=0.3, listen_only=True).run_port("COM5")
    assert result["found"] is False and written == []


def test_label_log_feeds_pieces_and_writes_files(tmp_path):
    log = LabelLog(str(tmp_path))
    profile = profiles.validate({"name": "label-1", "port": "COM8", "protocol": "label_print",
                                 "serial": {"baudrate": 9600}})
    a, b = capture()[3], capture()[4]
    assert log.feed(profile, a[:100]) == []
    got = log.feed(profile, a[100:] + b)
    assert [r["value"] for r in got] == [1.4, 1.4] and [r["seq"] for r in got] == [1, 2]
    assert [r["seq"] for r in log.list("label-1", after=1)] == [2]
    files = list(tmp_path.iterdir())
    assert len(files) == 1 and files[0].name.startswith("label-1-")
    lines = files[0].read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[0])["fields"]["Order.Co"] == "222"


def test_bridge_keeps_print_scale_open_and_logs_labels(tmp_path):
    from scale_bridge.config import Config
    from scale_bridge.server import Bridge
    config = Config(str(tmp_path / "bridge.json"))
    bridge = Bridge(config, simulate="label_print")
    try:
        config.save_profile({"name": "label-1", "port": "COM90", "protocol": "label_print",
                             "serial": {"baudrate": 9600}})
        bridge.keeper.tick()
        deadline = time.time() + 12
        while time.time() < deadline and not bridge.labels.list("label-1"):
            time.sleep(0.3)
        listed = bridge.label_list({"profile": "label-1"})
        assert listed["labels"] and listed["listening"] == ["label-1"]
        assert listed["labels"][-1]["fields"]["SHIFT"] == "2"
        started = time.monotonic()
        answer = bridge.weight(config.profile("label-1"), max_age_ms=60000, wait_ms=2500)
        assert time.monotonic() - started < 1.5          # a print scale never holds the caller
        assert answer["ok"] and answer["on_print"] and answer["stable"] and answer["unit"] == "kg"
        assert (tmp_path / "labels").is_dir()
    finally:
        bridge.keeper.stop()
        bridge.registry.stop_all()
