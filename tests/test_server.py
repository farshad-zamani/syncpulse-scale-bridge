# SPDX-License-Identifier: GPL-3.0-or-later
"""The HTTP interface, end to end, with simulated scales."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from scale_bridge.config import Config
from scale_bridge.detect import Timings
from scale_bridge.server import Bridge, make_server

LOCAL = {"X-Requested-With": "ScaleBridge"}


@pytest.fixture(scope="module")
def bridge_url(tmp_path_factory):
    config = Config(str(tmp_path_factory.mktemp("bridge") / "bridge.json"))
    bridge = Bridge(config, simulate="mahak_mds,toledo_cont:4800:7E1")
    bridge.detect_timings = Timings(passive_s=0.5, probe_s=0.15, confirm_s=0.4, drain_s=0.02)
    server = make_server(bridge, "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", config
    server.shutdown()
    bridge.registry.stop_all()


def call(url, method="GET", body=None, headers=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_health_is_open_and_identifies_the_author(bridge_url):
    url, _ = bridge_url
    code, body = call(url + "/health")
    assert code == 200 and body["service"] == "syncpulse-scale-bridge"
    assert body["author"] == "Farshad Zamani" and "weight" in body["capabilities"]


def test_key_is_required(bridge_url):
    url, config = bridge_url
    assert call(url + "/ports")[0] == 401
    assert call(url + "/ports", headers={"X-Bridge-Token": "wrong"})[0] == 401
    code, body = call(url + "/ports", headers={"X-Bridge-Token": config.token})
    assert code == 200 and any(p["device"] == "COM90" for p in body["ports"])


def test_legacy_read_contract(bridge_url):
    url, config = bridge_url
    code, body = call(url + "/read", "POST", {
        "serial": {"port": "COM90", "baudrate": 9600, "bytesize": 8, "parity": "N", "stopbits": 1},
        "exchange": {"request_hex": "4D 09 04 07", "poll_interval_ms": 300}, "frames": 3},
        headers={"X-Bridge-Token": config.token})
    assert code == 200 and body["ok"] and body["open"]
    assert body["frames"] and body["frames"][-1]["hex"].startswith("58")
    assert {"t", "hex"} <= set(body["frames"][-1]) and "now" in body


def test_weight_by_port_and_protocol(bridge_url):
    url, config = bridge_url
    code, body = call(url + "/weight?port=COM91&protocol=toledo_cont&baud=4800&framing=7E1",
                      headers={"X-Bridge-Token": config.token})
    assert code == 200 and body["ok"] and body["unit"] == "kg" and body["checksum_ok"] is True
    assert isinstance(body["value"], float) and "measured_at" in body


def test_weight_errors(bridge_url):
    url, config = bridge_url
    h = {"X-Bridge-Token": config.token}
    assert call(url + "/weight?profile=missing", headers=h)[0] == 404
    assert call(url + "/weight?port=COM90", headers=h)[0] == 400
    assert call(url + "/weight?port=COM90&protocol=mt_sics&framing=9X9", headers=h)[0] == 400


def test_local_api_needs_header_and_local_host(bridge_url):
    url, _ = bridge_url
    assert call(url + "/api/state")[0] == 403
    assert call(url + "/api/state", headers={**LOCAL, "Host": "evil.example"})[0] == 403
    code, state = call(url + "/api/state", headers=LOCAL)
    assert code == 200 and state["about"]["author"] == "Farshad Zamani" and state["token"]


def test_page_is_served_with_signature(bridge_url):
    url, _ = bridge_url
    with urllib.request.urlopen(url + "/", timeout=5) as r:
        html = r.read().decode("utf-8")
        assert "Content-Security-Policy" in r.headers
    assert "Farshad Zamani" in html and "linkedin.com/in/farshad-zamani92" in html
    assert "cloudtart.com" in html and "SyncPulse" in html


def test_detect_save_read_delete(bridge_url):
    url, config = bridge_url
    code, body = call(url + "/api/detect", "POST", {"ports": ["COM90"]}, headers=LOCAL)
    assert code == 200 and body["job"]["running"]
    # a second search while the first runs is refused, and the port is reserved
    assert call(url + "/api/detect", "POST", {"ports": ["COM90"]}, headers=LOCAL)[0] == 409
    busy = call(url + "/weight?port=COM90&protocol=mahak_mds", headers={"X-Bridge-Token": config.token})
    assert busy[0] == 409
    deadline = time.time() + 60
    job = None
    while time.time() < deadline:
        job = call(url + "/api/detect", headers=LOCAL)[1]["job"]
        if not job["running"]:
            break
        time.sleep(0.3)
    assert job and job["results"][0]["found"] and job["results"][0]["protocol"] == "mahak_mds"
    assert job["progress"] == 1.0

    code, saved = call(url + "/api/profiles", "POST",
                       {"detection": job["results"][0], "name": "packing-1", "label": "Packing"},
                       headers=LOCAL)
    assert code == 200 and saved["profile"]["name"] == "packing-1"

    code, listed = call(url + "/profiles", headers={"X-Bridge-Token": config.token})
    assert [p["name"] for p in listed["profiles"]] == ["packing-1"]

    deadline = time.time() + 10
    body = {}
    while time.time() < deadline:
        body = call(url + "/weight?profile=packing-1", headers={"X-Bridge-Token": config.token})[1]
        if body.get("stable"):
            break
        time.sleep(0.4)
    assert body["ok"] and body["unit"] == "g" and body["stable"] is True

    code, _ = call(url + "/api/profiles/packing-1", "DELETE", headers=LOCAL)
    assert code == 200 and config.profiles() == []


def test_allowed_clients_do_not_lock_out_this_pc(bridge_url):
    url, config = bridge_url
    code, _ = call(url + "/api/allowed", "POST", {"clients": ["10.1.2.3"]}, headers=LOCAL)
    assert code == 200
    try:
        assert call(url + "/ports", headers={"X-Bridge-Token": config.token})[0] == 200
    finally:
        call(url + "/api/allowed", "POST", {"clients": []}, headers=LOCAL)


def test_bad_json_is_a_400(bridge_url):
    url, config = bridge_url
    req = urllib.request.Request(url + "/read", method="POST", data=b"{nope",
                                 headers={"X-Bridge-Token": config.token})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=5)
    assert e.value.code == 400
