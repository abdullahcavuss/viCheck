"""
LabVIEW type table (VCTP) reader and flattened-data decoder.

pylabview writes the VI's consolidated type table into the main XML:

    <VCTP><Section>
      <!-- FlatTypeID 87: ... -->
      <TypeDesc Type="Cluster" Label="Event Data"> <TypeDesc TypeID="84"/> ... </TypeDesc>
      ...
      <TopLevel> <TypeDesc Index="1" FlatTypeID="1"/> ... </TopLevel>
    </Section></VCTP>

Heap objects refer to a type as "TypeID(n)" where n is a *heap* type id; the main XML maps
heap id -> consolidated id (in comments), and TopLevel maps consolidated id -> flat id.

Block diagram constants store their value as LabVIEW *flattened* data (big-endian, strings and
arrays length-prefixed, clusters as the plain concatenation of their elements). Values that are
all zero are stored shortened, so missing trailing bytes are read as zeros.
"""
import re
import struct
import xml.etree.ElementTree as ET

_INT = {"Int8": (1, True), "UInt8": (1, False), "Int16": (2, True), "UInt16": (2, False),
        "Int32": (4, True), "UInt32": (4, False), "Int64": (8, True), "UInt64": (8, False)}
_FLOAT = {"Float32": (4, ">f"), "Float64": (8, ">d")}


class _Stop(Exception):
    """Raised when a type cannot be decoded; the caller shows what it has so far."""


def _text(b):
    for enc in ("utf-8", "cp1254", "cp1252"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("latin-1")


def _short(t, n=40):
    t = t.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    return t if len(t) <= n else t[:n - 1] + "…"


class Types:
    def __init__(self, main_xml_path):
        self.ok = False
        self.flat = []
        self.top = {}
        self.heap = {}
        self.base = 0
        try:
            raw = open(main_xml_path, encoding="utf-8", errors="replace").read()
            self.heap = {int(a): int(b) for a, b in
                         re.findall(r"Heap TypeID\s+(\d+)\s*=\s*Consolidated TypeID\s+(\d+)", raw)}
            m = re.search(r"<!-- FlatTypeID (\d+):", raw)
            self.base = int(m.group(1)) if m else 0
            root = ET.parse(main_xml_path).getroot()
        except (OSError, ET.ParseError):
            return
        vctp = root.find(".//VCTP/Section")
        if vctp is None:
            vctp = root.find(".//VCTP")
        if vctp is None:
            return
        for el in vctp:
            if el.tag == "TypeDesc":
                self.flat.append(el)
            elif el.tag == "TopLevel":
                for t in el:
                    try:
                        self.top[int(t.get("Index"))] = int(t.get("FlatTypeID"))
                    except (TypeError, ValueError):
                        pass
        self.ok = True

    # ------------------------------------------------------------ lookup
    def flat_el(self, fid):
        i = fid - self.base
        return self.flat[i] if 0 <= i < len(self.flat) else None

    def heap_el(self, heap_type_text):
        m = re.search(r"\d+", heap_type_text or "")
        if not m:
            return None
        c = self.heap.get(int(m.group(0)))
        f = self.top.get(c) if c is not None else None
        return self.deref(self.flat_el(f)) if f is not None else None

    def deref(self, el, depth=0):
        """<TypeDesc TypeID="n"/> is a reference to flat type n."""
        while el is not None and el.get("Type") is None and el.get("TypeID") is not None and depth < 20:
            el = self.flat_el(int(el.get("TypeID")))
            depth += 1
        return el

    def unwrap(self, el):
        """TypeDef and alignment containers -> the real type."""
        el = self.deref(el)
        for _ in range(10):
            if el is None:
                return None
            if el.get("Type") in ("TypeDef", "AlignmntMarker"):
                inner = el.find("TypeDesc")
                lab = el.get("Label")
                el = self.deref(inner)
                if el is not None and lab and not el.get("Label"):
                    el = _Relabel(el, lab)
                continue
            return el
        return el

    def label(self, el):
        el = self.deref(el)
        if el is None:
            return None
        if el.get("Label"):
            return el.get("Label")
        if el.get("Type") in ("TypeDef", "AlignmntMarker"):
            return self.label(el.find("TypeDesc"))
        return None

    def fields(self, el):
        """Labels of the elements of a cluster type (empty if not a cluster)."""
        el = self.unwrap(el)
        if el is None or el.get("Type") != "Cluster":
            return []
        out = []
        for c in el.findall("TypeDesc"):
            d = self.deref(c)
            if d is not None and d.get("Type") == "AlignmntMarker" and not self.label(d):
                continue   # padding inside event data clusters
            out.append(self.label(c) or "?")
        return out

    # ------------------------------------------------------------ flattened data
    def decode(self, raw_hex, heap_type_text, limit=160):
        """Readable text for a constant's flattened value, or None if the type is not supported."""
        el = self.heap_el(heap_type_text)
        if el is None:
            return None
        try:
            b = bytes.fromhex(raw_hex or "")
        except ValueError:
            return None
        out = []
        try:
            text, _ = self._val(el, b, 0, out, 0)
        except _Stop:
            text = None
        if text is None:
            return None
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _bytes(self, b, pos, n):
        chunk = b[pos:pos + n]
        if len(chunk) < n:
            chunk = chunk + b"\0" * (n - len(chunk))   # shortened zeros
        return chunk

    def _val(self, el, b, pos, out, depth):
        el = self.unwrap(el)
        if el is None or depth > 12:
            raise _Stop()
        t = el.get("Type") or ""
        base = t[4:] if t.startswith("Unit") else t[3:] if t.startswith("Num") else t
        if t == "Boolean":
            return ("True" if self._bytes(b, pos, 1)[0] else "False"), pos + 1
        if base in _INT:
            n, signed = _INT[base]
            v = int.from_bytes(self._bytes(b, pos, n), "big", signed=signed)
            enum = [e.text or "" for e in el.findall("EnumLabel")]
            if enum and 0 <= v < len(enum):
                return '"%s"' % enum[v], pos + n
            return str(v), pos + n
        if base in _FLOAT:
            n, fmt = _FLOAT[base]
            return "%g" % struct.unpack(fmt, self._bytes(b, pos, n))[0], pos + n
        if base.startswith("Complex"):
            n, fmt = _FLOAT.get(base.replace("Complex", "Float"), (None, None))
            if n is None:
                raise _Stop()
            re_ = struct.unpack(fmt, self._bytes(b, pos, n))[0]
            im = struct.unpack(fmt, self._bytes(b, pos + n, n))[0]
            return "%g%+gi" % (re_, im), pos + 2 * n
        if t in ("String", "PasString", "CString"):
            n = int.from_bytes(self._bytes(b, pos, 4), "big")
            if n > len(b):
                raise _Stop()
            return '"%s"' % _short(_text(b[pos + 4:pos + 4 + n])), pos + 4 + n
        if t == "Path":
            if b[pos:pos + 4] != b"PTH0":
                return "<empty path>", pos + 8
            n = int.from_bytes(self._bytes(b, pos + 4, 4), "big")
            body = b[pos + 8:pos + 8 + n]
            parts, p = [], 4
            try:
                cnt = int.from_bytes(body[2:4], "big")
                for _ in range(cnt):
                    k = body[p]
                    parts.append(_text(body[p + 1:p + 1 + k]))
                    p += 1 + k
            except IndexError:
                pass
            return '"%s"' % _short("\\".join(parts) or "<empty path>"), pos + 8 + n
        if t == "Array":
            dims = max(1, len(el.findall("Dimension")))
            sizes = []
            for i in range(dims):
                sizes.append(int.from_bytes(self._bytes(b, pos, 4), "big"))
                pos += 4
            total = 1
            for s in sizes:
                total *= s
            if total > 100000:
                raise _Stop()
            elem = el.find("TypeDesc")
            items = []
            for i in range(total):
                v, pos = self._val(elem, b, pos, out, depth + 1)
                if i < 6:
                    items.append(v)
            more = ", …(%d)" % total if total > len(items) else ""
            return "[" + ", ".join(items) + more + "]", pos
        if t == "Cluster":
            parts = []
            for c in el.findall("TypeDesc"):
                lab = self.label(c)
                v, pos = self._val(c, b, pos, out, depth + 1)
                parts.append(("%s: %s" % (lab, v)) if lab else v)
            return "{" + ", ".join(parts) + "}", pos
        raise _Stop()   # refnums, variants, timestamps, waveforms… are not decoded


class _Relabel:
    """A type element seen through a typedef that carries the label."""

    def __init__(self, el, label):
        self._el, self._label = el, label

    def get(self, k, d=None):
        if k == "Label":
            return self._label
        return self._el.get(k, d)

    def find(self, *a):
        return self._el.find(*a)

    def findall(self, *a):
        return self._el.findall(*a)
