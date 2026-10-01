# SPDX-License-Identifier: GPL-3.0-or-later
"""Every parser against sample frames in the shapes the manufacturers document."""
import pytest

from scale_bridge.protocols import PROTOCOLS, convert, get_protocol, lines, norm_unit
from scale_bridge.simulator import frame_for


def one(protocol_id, data, params=None):
    readings = get_protocol(protocol_id, params).readings(data)
    assert readings, f"{protocol_id} read nothing from {data!r}"
    return readings[-1]


def toledo_frame(swa, swb, swc, digits, tare=b"000000"):
    body = bytes([0x02, swa, swb, swc]) + digits + tare + b"\r"
    return body + bytes([(-sum(b & 0x7F for b in body)) & 0x7F])


# -- Mettler Toledo ----------------------------------------------------------

def test_mt_sics_stable_and_dynamic():
    r = one("mt_sics", b"S S      0.550 kg\r\n")
    assert (r.value, r.unit, r.stable) == (0.55, "kg", True)
    r = one("mt_sics", b"S D     12.345 g\r\n")
    assert (r.value, r.unit, r.stable) == (12.345, "g", False)


def test_mt_sics_overload_and_error():
    assert one("mt_sics", b"S +\r\n").overload
    assert PROTOCOLS["mt_sics"].readings(b"S I\r\nES\r\n") == []


def test_toledo_continuous_decimal_point_units_and_checksum():
    # SWA: bit5 + count-by x1 (bit3) + dp code 3 (XXXXX.X); SWB: bit5 + kg (bit4)
    r = one("toledo_cont", toledo_frame(0x2B, 0x30, 0x20, b"012345"))
    assert (r.value, r.unit, r.stable, r.net, r.checksum_ok) == (1234.5, "kg", True, False, True)
    # motion + negative + net, grams in SWC
    r = one("toledo_cont", toledo_frame(0x2A, 0x20 | 0x08 | 0x02 | 0x01, 0x21, b"000550"))
    assert (r.value, r.unit, r.stable, r.net) == (-550, "g", False, True)
    # lb when SWB bit4 is clear, dp code 5 (X.XXX)
    r = one("toledo_cont", toledo_frame(0x2D, 0x20, 0x20, b"001210"))
    assert (r.value, r.unit) == (1.21, "lb")


def test_toledo_continuous_bad_checksum_is_flagged():
    frame = bytearray(toledo_frame(0x2B, 0x30, 0x20, b"012345"))
    frame[-1] ^= 0x01
    assert one("toledo_cont", bytes(frame)).checksum_ok is False


# -- A&D and friends -----------------------------------------------------------

@pytest.mark.parametrize("frame,value,unit,stable,net", [
    (b"ST,+00000.550  kg\r\n", 0.55, "kg", True, None),
    (b"US,-00001.20 kg\r\n", -1.2, "kg", False, None),
    (b"ST,GS,+0012.34kg\r\n", 12.34, "kg", True, False),
    (b"ST,NT,+0001.500 lb\r\n", 1.5, "lb", True, True),
    (b"QT,+000123.4 g\r\n", 123.4, "g", True, None),
])
def test_and_standard(frame, value, unit, stable, net):
    r = one("and_std", frame)
    assert (r.value, r.unit, r.stable, r.net) == (value, unit, stable, net)


def test_and_standard_overload():
    r = one("and_std", b"OL,+9999999 kg\r\n")
    assert r.overload and r.value is None


def test_sma_frames():
    r = one("sma", b"\n 1G       0.550kg \r")      # s r n m f, then the weight in 10 characters
    assert (r.value, r.unit, r.stable, r.net) == (0.55, "kg", True, False)
    r = one("sma", b"\n 1NM     12.500lb \r")
    assert (r.value, r.unit, r.stable, r.net) == (12.5, "lb", False, True)
    assert one("sma", b"\nO1G  ----------lb \r").overload


def test_nci():
    r = one("nci", b"\n  1.23lb\r\n00\r\x03")
    assert (r.value, r.unit, r.stable) == (1.23, "lb", True)
    r = one("nci", b"\n  1.23lb\r\n10\r\x03")
    assert r.stable is False


def test_ohaus():
    r = one("ohaus", b"     0.550 kg   \r\n")
    assert (r.value, r.unit, r.stable) == (0.55, "kg", True)
    assert one("ohaus", b"     0.550 kg ? \r\n").stable is False
    assert one("ohaus", b"    1.234 kg N\r\n").net is True


def test_sartorius_unit_missing_means_unstable():
    r = one("sartorius", b"+     0.550 kg  \r\n")
    assert (r.value, r.unit, r.stable) == (0.55, "kg", True)
    r = one("sartorius", b"+     0.550     \r\n")
    assert (r.value, r.stable) == (0.55, False)
    r = one("sartorius", b"N     +     1.234 kg\r\n")
    assert (r.value, r.net) == (1.234, True)


def test_cas_enq():
    r = one("cas_enq", b"\x06\x01\x02S  0.550kg\x03\x04")
    assert (r.value, r.unit, r.stable) == (0.55, "kg", True)


# -- XK3190 ---------------------------------------------------------------------

def test_xk3190_tf0_with_checksum():
    body = b"+0012342"
    x = 0
    for b in body:
        x ^= b
    frame = b"\x02" + body + f"{x >> 4:X}{x & 0xF:X}".encode() + b"\x03"
    r = one("xk3190_tf0", frame * 2)
    assert (r.value, r.checksum_ok) == (12.34, True)
    r = one("xk3190_tf0", b"\x02-0005003" + b"00" + b"\x03")
    assert r.value == -0.5 and r.checksum_ok is False


def test_xk3190_reversed_stream():
    r = one("xk3190_reversed", b"05.21000=05.21000=05.21000=")
    assert r.value == 12.5
    assert PROTOCOLS["xk3190_reversed"].readings(b"05.21000=") == []


# -- Mahak (field-tested) -----------------------------------------------------------

def test_mahak_field_capture():
    # Captured on a Mahak MDS 13000 with a 550 g weight: 58 ?? 07 07 00 02 26
    r = one("mahak_mds", bytes.fromhex("58 51 07 07 00 02 26"))
    assert (r.value, r.unit) == (550.0, "g")
    r = one("mahak_mds", bytes.fromhex("58 A3 07 07 00 02 EE"))
    assert r.value == 750.0


def test_mahak_ignores_boot_message():
    assert PROTOCOLS["mahak_mds"].readings(bytes.fromhex("42 03 04 01 42 4F 4F 54 0C 04 8C")) == []


# -- generic and custom ----------------------------------------------------------------

def test_generic_ascii():
    r = one("ascii_generic", b"G  12.50 kg\r\n")
    assert (r.value, r.unit) == (12.5, "kg")
    assert one("ascii_generic", b"US  3.2 kg\r\n").stable is False


def test_custom_binary_and_ascii():
    params = {"pattern": "58 ?? 07 07", "value_offset": 4, "value_length": 3, "unit": "g"}
    r = one("custom_binary", bytes.fromhex("58 51 07 07 00 02 26"), params)
    assert (r.value, r.unit) == (550.0, "g")
    r = one("custom_ascii", b"W: 12.5\r\n", {"regex": r"W:\s*([-\d.]+)", "unit": "kg"})
    assert (r.value, r.unit) == (12.5, "kg")
    assert get_protocol("custom_ascii").readings(b"W: 1\r\n") == []


# -- the simulator speaks what the parsers read --------------------------------------------

@pytest.mark.parametrize("pid", ["mt_sics", "and_std", "toledo_cont", "sma", "nci", "ohaus", "sartorius",
                                 "cas_enq", "xk3190_tf0", "xk3190_reversed", "mahak_mds"])
@pytest.mark.parametrize("kg,stable", [(0.55, True), (13.1, False)])
def test_simulator_round_trip(pid, kg, stable):
    frame = frame_for(pid, kg, stable)
    data = frame * 3 if pid == "xk3190_reversed" else frame
    r = PROTOCOLS[pid].readings(data)[-1]
    expected = kg * 1000 if pid == "mahak_mds" else kg
    assert r.value == pytest.approx(expected)
    if r.stable is not None and pid != "sartorius":
        assert r.stable == stable


# -- helpers ----------------------------------------------------------------------------

def test_units():
    assert norm_unit(b" KG ") == "kg" and norm_unit("lbs") == "lb" and norm_unit(None) == ""
    assert convert(550, "g", "kg") == pytest.approx(0.55)
    assert convert(1, "lb", "g") == pytest.approx(453.59237)
    assert convert(1, "kg", "pcs") is None


def test_lines_split_on_terminators():
    assert lines(b"\x02abc\r\ndef\x03\r\n\r\n") == [b"abc", b"def"]


def test_catalogue_is_consistent():
    from scale_bridge.protocols import CONTINUOUS_IDS, POLL_IDS
    for pid in CONTINUOUS_IDS + POLL_IDS:
        assert pid in PROTOCOLS
    for pid in POLL_IDS:
        assert PROTOCOLS[pid].request, pid
        # read-only: never zero / tare / reset / print-off letters on their own
        assert PROTOCOLS[pid].request.strip(b"\r\n") not in (b"Z", b"T", b"R", b"P")
