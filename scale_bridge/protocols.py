# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Farshad Zamani — Cloudtart (https://cloudtart.com)
"""
The protocol library: how scale indicators around the world put a weight on
a serial line, and how to ask for it.

Each protocol turns raw bytes into `Reading`s. `kind` says how the device
talks:

    continuous  it sends by itself, over and over — only listen
    poll        it answers a request; `request` is that request
    handshake   request -> ACK -> `after_ack` -> answer

Only READ-ONLY requests are used. Letters that zero, tare or switch off a
display on some brand (Z, T, R, and P — display on/off on A&D) are never
sent by auto-detection.

`field_tested` marks what has been verified on real hardware; the rest
follows the manufacturers' published formats and is covered by tests with
the sample frames those documents give.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

UNIT_ALIASES = {
    "kg": "kg", "kgs": "kg", "g": "g", "gr": "g", "t": "t", "ton": "t",
    "lb": "lb", "lbs": "lb", "#": "lb", "oz": "oz", "ozt": "ozt", "ct": "ct",
}
GRAMS_PER = {"g": 1.0, "kg": 1000.0, "t": 1_000_000.0, "lb": 453.59237, "oz": 28.349523125,
             "ozt": 31.1034768, "ct": 0.2}


def norm_unit(text: Any) -> str:
    if text is None:
        return ""
    raw = text.decode("latin-1") if isinstance(text, (bytes, bytearray)) else str(text)
    raw = raw.strip()
    return UNIT_ALIASES.get(raw.lower(), raw)


def convert(value: float, from_unit: str, to_unit: str) -> Optional[float]:
    """Convert between mass units; None when either unit is not a mass unit."""
    a, b = GRAMS_PER.get(from_unit), GRAMS_PER.get(to_unit)
    if a is None or b is None:
        return None
    return value * a / b


def _num(text: bytes) -> float:
    return float(text.replace(b" ", b"").replace(b",", b"."))


def lines(data: bytes) -> list[bytes]:
    """Complete lines: the text between terminators, empty ones dropped."""
    parts = re.split(rb"[\r\n\x03]+", data)
    return [p.strip(b"\x02\x00 ") for p in parts if p.strip(b"\x02\x00 ")]


@dataclass
class Reading:
    value: Optional[float]        # None: the frame carries no number (overload, error)
    unit: str = ""
    stable: Optional[bool] = None  # None: the protocol does not say
    net: Optional[bool] = None
    overload: bool = False
    raw: bytes = b""
    checksum_ok: Optional[bool] = None
    # Other values the frame carries (e.g. the order number on a label).
    fields: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        out = {"value": self.value, "unit": self.unit, "stable": self.stable, "net": self.net,
               "overload": self.overload, "raw_hex": self.raw.hex(" ").upper(),
               "checksum_ok": self.checksum_ok}
        if self.fields:
            out["fields"] = dict(self.fields)
        return out


@dataclass
class Protocol:
    id: str
    name: str
    kind: str = "continuous"
    request: bytes = b""
    after_ack: bytes = b""
    families: str = ""
    reference: str = ""
    field_tested: bool = False
    specificity: int = 2          # 1 generic … 3 strictly framed (wins ties in detection)
    default_poll_ms: int = 500
    # Readings auto-detection needs to see. A device that only sends when its
    # Print key is pressed may send just one.
    min_frames: int = 2
    params: dict = field(default_factory=dict)

    def readings(self, data: bytes) -> list[Reading]:     # pragma: no cover - abstract
        raise NotImplementedError

    def info(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "on_print": self.kind == "print",
                "request_hex": self.request.hex(" ").upper(),
                "after_ack_hex": self.after_ack.hex(" ").upper(),
                "families": self.families, "reference": self.reference,
                "field_tested": self.field_tested}


# ---------------------------------------------------------------------------
# Mettler Toledo
# ---------------------------------------------------------------------------

class MtSics(Protocol):
    """MT-SICS: 'SI' -> 'S S      0.550 kg' (S = stable, D = dynamic)."""
    _re = re.compile(rb"^S\s+([SD+\-])\s*([-+]?\s*\d+(?:[.,]\d+)?)?\s*([A-Za-z%#]{0,4})")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for line in lines(data):
            m = self._re.match(line)
            if not m:
                continue
            flag = m.group(1)
            if flag in (b"+", b"-"):
                out.append(Reading(None, overload=True, raw=line))
            elif m.group(2):
                out.append(Reading(_num(m.group(2)), norm_unit(m.group(3)),
                                   stable=flag == b"S", raw=line))
        return out


class ToledoContinuous(Protocol):
    """
    Toledo Continuous (Mettler Toledo standard continuous output, copied by
    many other indicators):

        STX SWA SWB SWC W W W W W W T T T T T T CR [CHK]

    SWA bits 0-2 place the decimal point (X00, X0, X, 0.X ... 0.0000X);
    SWB bit0 net, bit1 negative, bit2 over/under range, bit3 motion,
    bit4 kg (else lb); SWC bits 0-2 override the unit (1 g, 2 t, 3 oz).
    Bit 5 of each status byte is always set. CHK is the two's complement of
    the 7-bit sum of STX..CR.
    """
    _re = re.compile(rb"\x02([\x20-\x7f])([\x20-\x7f])([\x20-\x7f])([0-9 ]{6})([0-9 ]{6})\r(.?)",
                     re.S)
    _factor = {0: 100, 1: 10, 2: 1, 3: 0.1, 4: 0.01, 5: 0.001, 6: 0.0001, 7: 0.00001}
    _decimals = {0: 0, 1: 0, 2: 0, 3: 1, 4: 2, 5: 3, 6: 4, 7: 5}

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for m in self._re.finditer(data):
            swa, swb, swc = m.group(1)[0], m.group(2)[0], m.group(3)[0]
            if not (swa & 0x20 and swb & 0x20 and swc & 0x20):
                continue
            dp = swa & 0x07
            value = round(int(m.group(4).replace(b" ", b"0")) * self._factor[dp], self._decimals[dp])
            if swb & 0x02:
                value = -value
            unit = {1: "g", 2: "t", 3: "oz"}.get(swc & 0x07, "kg" if swb & 0x10 else "lb")
            frame = data[m.start():m.end(5) + 1]
            checksum_ok = None
            if m.group(6) and m.group(6) != b"\x02":
                checksum_ok = ((-sum(b & 0x7F for b in frame)) & 0x7F) == (m.group(6)[0] & 0x7F)
            out.append(Reading(value, unit, stable=not (swb & 0x08), net=bool(swb & 0x01),
                               overload=bool(swb & 0x04), raw=frame, checksum_ok=checksum_ok))
        return out


# ---------------------------------------------------------------------------
# A&D and the many indicators that copy its format
# ---------------------------------------------------------------------------

class AndStandard(Protocol):
    """'ST,+00000.55  kg', 'US,GS,+0012.34kg', 'OL,+9999999 kg' (ST stable, US unstable, OL overload)."""
    _re = re.compile(rb"^(ST|US|OL|QT|WT)\s*,\s*(?:(GS|NT|TR|G|N)\s*,\s*)?([-+])?\s*(\d+(?:[.,]\d+)?)?\s*"
                     rb"([A-Za-z%#]{0,4})")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for line in lines(data):
            m = self._re.match(line)
            if not m:
                continue
            head = m.group(1)
            net = {b"NT": True, b"N": True, b"GS": False, b"G": False}.get(m.group(2))
            if head == b"OL" or not m.group(4):
                out.append(Reading(None, overload=head == b"OL", net=net, raw=line))
                continue
            value = _num(m.group(4)) * (-1 if m.group(3) == b"-" else 1)
            out.append(Reading(value, norm_unit(m.group(5)), stable=head in (b"ST", b"QT"),
                               net=net, raw=line))
        return out


# ---------------------------------------------------------------------------
# SMA (Scale Manufacturers Association) and NCI 3835
# ---------------------------------------------------------------------------

class Sma(Protocol):
    """
    SMA SCP-0499: '<LF>W<CR>' -> '<LF><s><r><n><m><f><weight:10><unit:3><CR>'.
    s = Z/O/U/E/I/T/space, r = range, n = G/T/N, m = 'M' in motion.
    """
    _re = re.compile(rb"\n([ ZOUEIT])([ 0-9])([GTNgtn])([M ])([ -~])([ -~]{10})([ -~]{1,3})\r")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for m in self._re.finditer(data):
            field_text = m.group(6).strip()
            status = m.group(1)
            try:
                value = _num(field_text) if re.fullmatch(rb"[-+]?\d+(?:\.\d+)?", field_text) else None
            except ValueError:
                value = None
            out.append(Reading(value, norm_unit(m.group(7)), stable=m.group(4) != b"M",
                               net=m.group(3) in (b"N", b"n"), overload=status in (b"O", b"U"),
                               raw=m.group(0)))
        return out


class Nci(Protocol):
    """NCI 3835: 'W<CR>' -> '<LF>  1.23lb<CR><LF>hh<CR><ETX>' (hh status, bit0 of h1 = motion)."""
    _re = re.compile(rb"\n\s*([-+]?\s*\d+(?:\.\d+)?)\s*(lb|kg|g|oz|LB|KG|G|OZ)\s*\r(?:\n(.)(.)\r)?", re.S)

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for m in self._re.finditer(data):
            stable = None if m.group(3) is None else not (m.group(3)[0] & 0x01)
            out.append(Reading(_num(m.group(1)), norm_unit(m.group(2)), stable=stable, raw=m.group(0)))
        return out


# ---------------------------------------------------------------------------
# Ohaus, Sartorius
# ---------------------------------------------------------------------------

class Ohaus(Protocol):
    """'IP' -> '     0.550 kg   ' ('?' after the unit when unstable, optional G/N)."""
    _re = re.compile(rb"^([-+]?\s*\d+(?:[.,]\d+)?)\s*([A-Za-z%#]{1,4})\s*(\?)?\s*([GNT])?\s*$")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for line in lines(data):
            m = self._re.match(line)
            if m:
                out.append(Reading(_num(m.group(1)), norm_unit(m.group(2)), stable=m.group(3) is None,
                                   net={b"N": True, b"G": False}.get(m.group(4)), raw=line))
        return out


class Sartorius(Protocol):
    """
    Sartorius SBI: 'ESC P' -> '+     0.550 kg  ' or 'N     +     0.550 kg'.
    An unstable value is sent WITHOUT its unit — that is the stability flag.
    """
    _re = re.compile(rb"^(?:([A-Za-z#]{1,6})\s+)?([-+])\s*(\d+(?:[.,]\d+)?)\s*([A-Za-z%]{0,4})\s*$")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for line in lines(data):
            m = self._re.match(line)
            if not m:
                continue
            value = _num(m.group(3)) * (-1 if m.group(2) == b"-" else 1)
            ident = (m.group(1) or b"").upper()
            out.append(Reading(value, norm_unit(m.group(4)), stable=bool(m.group(4)),
                               net=True if ident.startswith(b"N") else (False if ident.startswith(b"G") else None),
                               raw=line))
        return out


# ---------------------------------------------------------------------------
# CAS (ENQ/ACK/DC1)
# ---------------------------------------------------------------------------

class CasEnq(Protocol):
    """ENQ -> ACK, DC1 -> '...S/U ... weight unit...'. Parsed loosely; experimental."""
    _re = re.compile(rb"([SU])[ ,A-Z]*?([-+ ])?\s*(\d+(?:\.\d+)?)\s*(kg|g|lb|oz|KG|LB|OZ|G)")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for m in self._re.finditer(data):
            value = _num(m.group(3)) * (-1 if m.group(2) == b"-" else 1)
            out.append(Reading(value, norm_unit(m.group(4)), stable=m.group(1) == b"S", raw=m.group(0)))
        return out


# ---------------------------------------------------------------------------
# Chinese XK3190 family (Yaohua and compatibles)
# ---------------------------------------------------------------------------

class Xk3190Continuous(Protocol):
    """
    XK3190 continuous mode (tF=0), 12 bytes:
    STX, sign, 6 digits (high first), decimals (0-4), XOR high nibble, XOR low nibble, ETX.
    XOR covers the sign through the decimals byte. No unit is sent.
    """
    _re = re.compile(rb"\x02([+-])(\d{6})([0-4])(..)\x03", re.S)

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for m in self._re.finditer(data):
            body = m.group(1) + m.group(2) + m.group(3)
            x = 0
            for b in body:
                x ^= b
            got = m.group(4)
            hex_form = f"{x >> 4:X}{x & 0xF:X}".encode()
            nibble_form = bytes([0x30 + (x >> 4), 0x30 + (x & 0xF)])
            decimals = int(m.group(3))
            value = round(int(m.group(2)) / (10 ** decimals), decimals) * (-1 if m.group(1) == b"-" else 1)
            out.append(Reading(value, "", raw=m.group(0),
                               checksum_ok=got.upper() in (hex_form, nibble_form)))
        return out


class Xk3190Reversed(Protocol):
    """
    XK3190 'D2+' continuous modes (tF=2/3): the displayed weight with its
    characters REVERSED, frames separated by '='. 70.15 kg -> '51.07000='.
    """
    _token = re.compile(rb"^[-0-9.]{5,10}$")

    def readings(self, data: bytes) -> list[Reading]:
        if data.count(b"=") < 2:
            return []
        out = []
        for token in data.split(b"=")[1:-1]:
            token = token.strip()
            if not self._token.match(token) or token.count(b".") > 1:
                continue
            try:
                value = float(token[::-1])
            except ValueError:
                continue
            out.append(Reading(value, "", raw=b"=" + token))
        return out


# ---------------------------------------------------------------------------
# Mahak (Iran) — field-tested
# ---------------------------------------------------------------------------

class MahakMds(Protocol):
    """
    Mahak MDS series (e.g. MDS 13000, older firmware): request 4D 09 04 07,
    reply 58 ?? 07 07 W2 W1 W0 — grams, 24-bit big-endian. The scale's menu
    must be set to Serial mode. Byte 1 varies and is ignored.
    """
    _re = re.compile(rb"\x58.\x07\x07(...)", re.S)

    def readings(self, data: bytes) -> list[Reading]:
        return [Reading(float(int.from_bytes(m.group(1), "big")), "g", raw=m.group(0))
                for m in self._re.finditer(data)]


# ---------------------------------------------------------------------------
# Label printer streams — indicators wired to a label printer
# ---------------------------------------------------------------------------

_KV = re.compile(r"([A-Za-z][A-Za-z0-9_.]*)\s*:\s*(.*?)(?=\s+[A-Za-z][A-Za-z0-9_.]*\s*:|$)")
_DATE = re.compile(r"\b(\d{2,4}[/.-]\d{1,2}[/.-]\d{1,4})\b(?:\s*-?\s*(\d{1,2}:\d{2}(?::\d{2})?))?")
_NUMBER = re.compile(r"^[-+]?\s*\d+(?:[.,]\d+)?$")
_NUMBER_UNIT = re.compile(r"^([-+]?\s*\d+(?:[.,]\d+)?)\s*\(?\s*(kg|g|t|lb|lbs|oz)\s*\)?$", re.I)
_WEIGHT_WORD = re.compile(r"(weight|wt|net|gross|n\.?w|g\.?w|\u0648\u0632\u0646)\s*[:=]?\s*([-+]?\d+(?:[.,]\d+)?)\s*\(?\s*(kg|g|t|lb|oz)?",
                          re.I)


def _unit_only(text: str) -> str:
    t = text.strip().strip("()[]").strip()
    return norm_unit(t) if norm_unit(t) in GRAMS_PER else ""


class LabelPrinter(Protocol):
    """
    An indicator that prints labels: on its Print key it sends the whole label
    program to a label printer — TSPL/TSPL2 (TSC and compatibles), EPL2 (Zebra/
    Eltron, Argox) or ZPL (Zebra). Listening to that line (a Y cable leaves the
    printer connected) gives the weight the operator printed, plus whatever
    else the label carries: order number, shift, date, thickness …

    One reading per printed label (TSPL `PRINT`, EPL `P`, ZPL `^XZ`). The weight
    is the number printed next to a weight unit — "141.800" followed by "(Kg)",
    or "1.25 kg" in one text — or after a word such as Weight/Net/Gross/وزن.
    A printed weight counts as stable: indicators print settled weights.
    """
    _tspl_text = re.compile(rb'^(?:TEXT|BLOCK)\s[^"]*"[^"]*"[^"]*?"(.*?)"?\s*$')
    _tspl_barcode = re.compile(rb'^BARCODE\s[^"]*"[^"]*"[^"]*?"(.*?)"?\s*$')
    _epl_text = re.compile(rb'^A\d+,\d+,[^"]*"(.*?)"?\s*$')
    _epl_barcode = re.compile(rb'^B\d+,\d+,[^"]*"(.*?)"?\s*$')
    _zpl_field = re.compile(rb"\^FD(.*?)\^FS", re.S)
    _end = re.compile(rb"(?:^|[\r\n])(?:PRINT\s+\d+(?:\s*,\s*\d+)?|P\d+(?:,\d+)?)\s*(?=[\r\n]|$)|\^XZ")

    def _texts(self, label: bytes) -> tuple[list[str], list[str]]:
        texts: list[str] = []
        codes: list[str] = []
        if b"^FD" in label:
            for m in self._zpl_field.finditer(label):
                texts.append(m.group(1).decode("latin-1"))
            return texts, codes
        for line in re.split(rb"[\r\n]+", label):
            line = line.strip()
            for rx, bucket in ((self._tspl_text, texts), (self._tspl_barcode, codes),
                               (self._epl_text, texts), (self._epl_barcode, codes)):
                m = rx.match(line)
                if m:
                    bucket.append(m.group(1).decode("latin-1"))
                    break
        return texts, codes

    def _weight(self, texts: list[str]) -> Optional[tuple[float, str]]:
        clean = [t.strip() for t in texts]
        for i, t in enumerate(clean):
            m = _NUMBER_UNIT.match(t)
            if m:
                return _num(m.group(1).encode()), norm_unit(m.group(2))
            if _NUMBER.match(t):
                for j in (i + 1, i - 1):
                    if 0 <= j < len(clean) and _unit_only(clean[j]):
                        return _num(t.encode()), _unit_only(clean[j])
        for t in clean:
            m = _WEIGHT_WORD.search(t)
            if m:
                return _num(m.group(2).encode()), norm_unit(m.group(3) or "")
        return None

    @staticmethod
    def _fields(texts: list[str], codes: list[str]) -> dict:
        fields: dict[str, str] = {}
        for t in texts:
            d = _DATE.search(t)
            if d and "date" not in fields:
                fields["date"] = d.group(1)
                if d.group(2):
                    fields["time"] = d.group(2)
                continue
            for key, value in _KV.findall(t):
                value = value.strip().strip('"').strip()
                if value:
                    fields.setdefault(key.strip(), value)
        if codes:
            fields["barcode"] = codes[0].replace("\t", " | ").strip()
        return fields

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        start = 0
        for end in self._end.finditer(data):
            label = data[start:end.end()]
            start = end.end()
            texts, codes = self._texts(label)
            found = self._weight(texts)
            if found is None:
                continue
            value, unit = found
            out.append(Reading(value, unit, stable=True, raw=label.strip(b"\r\n"),
                               fields=self._fields(texts, codes)))
        return out


# ---------------------------------------------------------------------------
# Generic and custom
# ---------------------------------------------------------------------------

class GenericAscii(Protocol):
    """Any readable line with a number in it — the last resort for continuous output."""
    _re = re.compile(rb"([-+]?\s*\d+(?:[.,]\d+)?)\s*(kg|g|lb|lbs|oz|t|KG|G|LB|OZ|T)?\b")
    _stable_words = re.compile(rb"\b(ST|S)\b")
    _unstable_words = re.compile(rb"\b(US|D|M|MOTION)\b|\?")

    def readings(self, data: bytes) -> list[Reading]:
        out = []
        for line in lines(data):
            if len(line) > 80 or sum(32 <= b < 127 for b in line) < len(line) * 0.9:
                continue
            numbers = list(self._re.finditer(line))
            if not numbers:
                continue
            m = numbers[-1]
            stable = None
            if self._unstable_words.search(line):
                stable = False
            elif self._stable_words.search(line):
                stable = True
            out.append(Reading(_num(m.group(1)), norm_unit(m.group(2)), stable=stable, raw=line))
        return out


class CustomBinary(Protocol):
    """
    A binary frame described by hand: `pattern` (hex, '??' = any byte), then
    `value_length` bytes at `value_offset` from the pattern's first byte.
    """

    def readings(self, data: bytes) -> list[Reading]:
        p = self.params
        pattern = [None if t == "??" else int(t, 16) for t in str(p.get("pattern") or "").split()]
        offset = int(p.get("value_offset") or 0)
        length = int(p.get("value_length") or 1)
        order = "little" if p.get("byte_order") == "little" else "big"
        signed = bool(p.get("signed"))
        unit = norm_unit(p.get("unit") or "")
        out = []
        n = len(pattern)
        starts = [0] if not n else [
            i for i in range(0, len(data) - n + 1)
            if all(b is None or data[i + k] == b for k, b in enumerate(pattern))]
        for start in starts:
            end = start + offset + length
            if end > len(data):
                continue
            value = int.from_bytes(data[start + offset:end], order, signed=signed)
            out.append(Reading(float(value), unit, raw=data[start:max(end, start + n)]))
        return out


class CustomAscii(Protocol):
    """Any text format described by hand: the first group of `regex` is the number."""

    def readings(self, data: bytes) -> list[Reading]:
        regex = str(self.params.get("regex") or "")
        if not regex:
            return []
        compiled = re.compile(regex.encode("latin-1"))
        unit = norm_unit(self.params.get("unit") or "")
        out = []
        for line in lines(data):
            m = compiled.search(line)
            if m and m.groups() and m.group(1):
                try:
                    out.append(Reading(_num(m.group(1)), unit, raw=line))
                except ValueError:
                    continue
        return out


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

def _catalogue() -> dict[str, Protocol]:
    items: Iterable[Protocol] = [
        MtSics("mt_sics", "Mettler Toledo MT-SICS", kind="poll", request=b"SI\r\n", specificity=3,
               families="Mettler Toledo terminals and balances (IND, ICS, XS, ML…)",
               reference="MT-SICS reference manual"),
        ToledoContinuous("toledo_cont", "Toledo Continuous (STX + status words)", specificity=3,
                         families="Mettler Toledo IND/Panther/Jaguar/Lynx and many compatible indicators",
                         reference="Mettler Toledo 'Standard continuous output' (e.g. IND425 manual 4.2)"),
        AndStandard("and_std", "A&D standard format (ST/US/OL)", kind="poll", request=b"Q\r\n",
                    specificity=3,
                    families="A&D indicators/balances and many Asian indicators (continuous or on request)",
                    reference="A&D indicator manuals, data format section"),
        Sma("sma", "SMA standard (Scale Manufacturers Association)", kind="poll", request=b"\nW\r",
            specificity=3, families="Rice Lake, Avery Weigh-Tronix, Cardinal, Fairbanks and other SMA-compliant indicators",
            reference="SMA SCP-0499"),
        Nci("nci", "NCI 3835 / Weigh-Tronix", kind="poll", request=b"W\r", specificity=2,
            families="NCI / Avery Weigh-Tronix shipping and bench scales",
            reference="NCI 3835 protocol"),
        Ohaus("ohaus", "Ohaus", kind="poll", request=b"IP\r\n", specificity=2,
              families="Ohaus Defender, Ranger, Valor and compatible indicators",
              reference="Ohaus interface command table (IP = immediate print)"),
        Sartorius("sartorius", "Sartorius SBI", kind="poll", request=b"\x1bP\r\n", specificity=2,
                  families="Sartorius balances and Combics/Signum indicators",
                  reference="Sartorius SBI data output format"),
        CasEnq("cas_enq", "CAS (ENQ/ACK/DC1), experimental", kind="handshake", request=b"\x05",
               after_ack=b"\x11", specificity=2, families="CAS scales and compatibles",
               reference="CAS ENQ/ACK polling"),
        Xk3190Continuous("xk3190_tf0", "XK3190 continuous (tF=0)", specificity=3,
                         families="Yaohua XK3190-A9/A12 and compatible Chinese indicators",
                         reference="XK3190-A9+ user manual, serial output"),
        Xk3190Reversed("xk3190_reversed", "XK3190 '=' reversed-digit stream (tF=2/3)", specificity=2,
                       families="Yaohua XK3190 series and compatible Chinese indicators/big displays",
                       reference="XK3190-A9+ user manual, D2+ continuous mode"),
        MahakMds("mahak_mds", "Mahak MDS binary (4D 09 04 07)", kind="poll",
                 request=bytes.fromhex("4D090407"), specificity=3, field_tested=True,
                 families="Mahak MDS 13000 and related Mahak scales (Iran), Serial mode",
                 reference="Mahak developer guide + field test"),
        LabelPrinter("label_print", "Label printer stream (TSPL / EPL / ZPL)", kind="print",
                     specificity=3, min_frames=1, field_tested=True,
                     families="Indicators wired to a label printer (TSC, Zebra, Argox…); sends on Print. "
                              "Tested on a PTC400 indicator (TSPL)",
                     reference="TSC TSPL/TSPL2, Zebra EPL2 and ZPL programming manuals + field test"),
        GenericAscii("ascii_generic", "Generic text (number + unit)", specificity=1,
                     families="Any indicator that streams readable weight text",
                     reference="heuristic"),
        CustomBinary("custom_binary", "Custom binary frame", kind="poll", specificity=0,
                     reference="configured by hand"),
        CustomAscii("custom_ascii", "Custom text (regular expression)", kind="poll", specificity=0,
                    reference="configured by hand"),
    ]
    return {p.id: p for p in items}


PROTOCOLS: dict[str, Protocol] = _catalogue()

# Detection order. Continuous formats are tried on whatever a port sends by
# itself; poll protocols are asked in turn when it sends nothing.
CONTINUOUS_IDS = ["label_print", "toledo_cont", "xk3190_tf0", "and_std", "mt_sics", "sma",
                  "xk3190_reversed", "ohaus", "sartorius", "ascii_generic"]
POLL_IDS = ["mt_sics", "and_std", "sma", "nci", "ohaus", "sartorius", "mahak_mds", "cas_enq"]


def get_protocol(protocol_id: str, params: Optional[dict] = None) -> Protocol:
    base = PROTOCOLS.get(protocol_id)
    if base is None:
        raise KeyError(f"unknown protocol: {protocol_id}")
    if params:
        clone = type(base)(**{**base.__dict__, "params": dict(params)})
        return clone
    return base


def catalogue_info() -> list[dict[str, Any]]:
    return [p.info() for p in PROTOCOLS.values()]
