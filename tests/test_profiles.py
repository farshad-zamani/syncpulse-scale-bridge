# SPDX-License-Identifier: GPL-3.0-or-later
import json

import pytest

from scale_bridge import profiles
from scale_bridge.config import Config
from scale_bridge.protocols import Reading


def base(**over):
    raw = {"name": "packing-1", "port": "com7", "protocol": "mahak_mds",
           "serial": {"baudrate": 9600}, "exchange": {"request_hex": "4d090407"}}
    raw.update(over)
    return raw


def test_validate_normalises():
    p = profiles.validate(base())
    assert p["port"] == "COM7"
    assert p["serial"]["baudrate"] == 9600 and p["serial"]["parity"] == "N"
    assert p["exchange"]["request_hex"] == "4D 09 04 07"
    assert p["stable_samples"] == 3


@pytest.mark.parametrize("bad", [
    {"name": ""}, {"name": "bad name"}, {"name": "-x"}, {"protocol": "nope"}, {"port": "LPT1"},
    {"serial": {"baudrate": 9}}, {"exchange": {"request_hex": "zz"}}, {"output_unit": "pcs"},
    {"protocol": "custom_ascii", "params": {"regex": "("}}, {"protocol": "custom_ascii", "params": {}},
])
def test_validate_rejects(bad):
    with pytest.raises(ValueError):
        profiles.validate(base(**bad))


class FakeWorker:
    def __init__(self, chunks, is_open=True, last_error=None):
        self.chunks = chunks
        self.is_open = is_open
        self.last_error = last_error

    def recent(self, count):
        return self.chunks[-count:]


MAHAK = lambda grams: bytes([0x58, 0x51, 7, 7]) + grams.to_bytes(3, "big")   # noqa: E731


def test_evaluate_flagless_stability_needs_equal_recent_readings():
    p = profiles.validate(base())
    now = 100_000
    moving = FakeWorker([(now - 1000, MAHAK(540)), (now - 500, MAHAK(550)), (now - 10, MAHAK(550))])
    r = profiles.evaluate(p, moving, 1500, now)
    assert r["ok"] and r["value"] == 550 and r["unit"] == "g" and r["stable"] is False
    steady = FakeWorker([(now - 1000, MAHAK(550)), (now - 500, MAHAK(550)), (now - 10, MAHAK(550))])
    assert profiles.evaluate(p, steady, 1500, now)["stable"] is True
    old = FakeWorker([(now - 60_000, MAHAK(550)), (now - 59_000, MAHAK(550)), (now - 10, MAHAK(550))])
    assert profiles.evaluate(p, old, 1500, now)["stable"] is False


def test_evaluate_stale_and_conversion():
    p = profiles.validate(base(output_unit="kg"))
    now = 100_000
    r = profiles.evaluate(p, FakeWorker([(now - 5000, MAHAK(550))] * 3), 1500, now)
    assert r["stale"] is True and r["stable"] is False
    assert r["value"] == pytest.approx(0.55) and r["unit"] == "kg"


def test_evaluate_unit_fallback_for_unitless_protocols():
    p = profiles.validate(base(protocol="xk3190_reversed", unit="kg", exchange={}))
    r = profiles.evaluate(p, FakeWorker([(1000, b"05.21000=05.21000=05.21000=")]), 1500, 1010)
    assert r["value"] == 12.5 and r["unit"] == "kg"


def test_evaluate_errors():
    p = profiles.validate(base())
    r = profiles.evaluate(p, FakeWorker([], is_open=False, last_error="could not open port COM7"), 1500, 0)
    assert r["ok"] is False and "COM7" in r["error"]
    r = profiles.evaluate(p, FakeWorker([(0, b"garbage")]), 1500, 10)
    assert r["ok"] is False and "protocol" in r["error"]


def test_from_detection_and_ad_hoc():
    detection = {"port": "COM9", "protocol": "xk3190_tf0",
                 "serial": {"port": "COM9", "baudrate": 2400, "bytesize": 8, "parity": "N", "stopbits": 1},
                 "exchange": {"request_hex": "", "poll_interval_ms": 500}, "reading": {"unit": ""}}
    p = profiles.from_detection(detection, "line-2")
    assert p["unit"] == "kg" and p["serial"]["baudrate"] == 2400
    q = profiles.ad_hoc("COM3", "mt_sics")
    assert q["exchange"]["request_hex"] == "53 49 0D 0A"


def test_config_round_trip_and_legacy_file(tmp_path):
    path = tmp_path / "bridge.json"
    # a file written by SyncPulse Serial Bridge 1.x
    path.write_text(json.dumps({"listen_host": "0.0.0.0", "listen_port": 8765, "token": "abc",
                                "allowed_clients": []}), encoding="utf-8")
    c = Config(str(path))
    assert c.token == "abc" and c.profiles() == []
    c.save_profile(base())
    assert Config(str(path)).profile("PACKING-1")["port"] == "COM7"
    assert c.delete_profile("packing-1") and not c.delete_profile("packing-1")
    with pytest.raises(ValueError):
        c.set_allowed_clients(["not-an-ip"])


def test_config_creates_token_and_survives_a_broken_file(tmp_path):
    path = tmp_path / "bridge.json"
    path.write_text("{broken", encoding="utf-8")
    c = Config(str(path))
    assert len(c.token) >= 24
    assert (tmp_path / "bridge.json.broken").exists()
    old = c.token
    assert c.rotate_token() != old


def test_reversed_stream_one_frame_per_chunk():
    # A Yaohua YH-T7E sends "=081.100" about nine times a second with a pause
    # between frames, so every frame lands in its own chunk (field capture, 1.18 kg).
    p = profiles.validate(base(protocol="xk3190_reversed", unit="kg", exchange={}))
    now = 10_000
    chunks = [(now - 400 + i * 100, b"=081.100") for i in range(5)]
    timed = profiles.timed_readings("xk3190_reversed", None, chunks)
    assert [x.reading.value for x in timed] == [1.18] * 4
    r = profiles.evaluate(p, FakeWorker(chunks), 1500, now)
    assert r["ok"] and r["value"] == 1.18 and r["unit"] == "kg" and r["stable"] is True


def test_chunk_boundaries_do_not_repeat_readings():
    frame = bytes([0x58, 0x51, 7, 7]) + (550).to_bytes(3, "big")
    timed = profiles.timed_readings("mahak_mds", None, [(1, frame), (2, frame), (3, frame)])
    assert [x.t_ms for x in timed] == [1, 2, 3]
