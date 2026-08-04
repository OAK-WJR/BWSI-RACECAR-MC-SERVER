#!/usr/bin/env python3
"""Zero-dependency NBT read/write, enough for schematics and player .dat.

Values keep their tag types via thin wrappers so a parsed tree can be
re-serialized without guessing. Round-trip is byte-exact for the files this
server produces (verify before trusting edits).
"""
import gzip
import struct
from pathlib import Path


class Byte(int): tag = 1
class Short(int): tag = 2
class Int(int): tag = 3
class Long(int): tag = 4
class Float(float): tag = 5
class Double(float): tag = 6
class ByteArray(bytes): tag = 7
class String(str): tag = 8


class List(list):
    tag = 9

    def __init__(self, etype, items=()):
        super().__init__(items)
        self.etype = etype


class Compound(dict): tag = 10
class IntArray(list): tag = 11
class LongArray(list): tag = 12


class _R:
    def __init__(self, b):
        self.b, self.i = b, 0

    def take(self, n):
        v = self.b[self.i:self.i + n]
        self.i += n
        return v

    def u1(self):
        return self.take(1)[0]

    def s2(self):
        return struct.unpack(">h", self.take(2))[0]

    def s4(self):
        return struct.unpack(">i", self.take(4))[0]

    def name(self):
        return self.take(struct.unpack(">H", self.take(2))[0]).decode("utf-8", "replace")


def _read(r, t):
    if t == 1: return Byte(struct.unpack(">b", r.take(1))[0])
    if t == 2: return Short(r.s2())
    if t == 3: return Int(r.s4())
    if t == 4: return Long(struct.unpack(">q", r.take(8))[0])
    if t == 5: return Float(struct.unpack(">f", r.take(4))[0])
    if t == 6: return Double(struct.unpack(">d", r.take(8))[0])
    if t == 7: return ByteArray(r.take(r.s4()))
    if t == 8: return String(r.name())
    if t == 9:
        et, n = r.u1(), r.s4()
        return List(et, [_read(r, et) for _ in range(n)])
    if t == 10:
        d = Compound()
        while True:
            ct = r.u1()
            if ct == 0:
                return d
            # NB: key must be read BEFORE the value — `d[r.name()] = _read(...)`
            # evaluates the right-hand side first and corrupts the stream
            key = r.name()
            d[key] = _read(r, ct)
    if t == 11: return IntArray([r.s4() for _ in range(r.s4())])
    if t == 12: return LongArray([struct.unpack(">q", r.take(8))[0] for _ in range(r.s4())])
    raise ValueError(f"tag {t}")


def _write(out, v):
    t = v.tag
    if t == 1: out += struct.pack(">b", int(v))
    elif t == 2: out += struct.pack(">h", int(v))
    elif t == 3: out += struct.pack(">i", int(v))
    elif t == 4: out += struct.pack(">q", int(v))
    elif t == 5: out += struct.pack(">f", float(v))
    elif t == 6: out += struct.pack(">d", float(v))
    elif t == 7: out += struct.pack(">i", len(v)) + v
    elif t == 8:
        b = v.encode("utf-8")
        out += struct.pack(">H", len(b)) + b
    elif t == 9:
        out += struct.pack(">bi", v.etype, len(v))
        for item in v:
            _write(out, item)
    elif t == 10:
        for k, item in v.items():
            kb = k.encode("utf-8")
            out += struct.pack(">b", item.tag) + struct.pack(">H", len(kb)) + kb
            _write(out, item)
        out += b"\x00"
    elif t == 11:
        out += struct.pack(">i", len(v))
        for x in v:
            out += struct.pack(">i", x)
    elif t == 12:
        out += struct.pack(">i", len(v))
        for x in v:
            out += struct.pack(">q", x)
    else:
        raise ValueError(f"tag {t}")


def load(path):
    raw = Path(path).read_bytes()
    gz = raw[:2] == b"\x1f\x8b"
    if gz:
        raw = gzip.decompress(raw)
    r = _R(raw)
    t = r.u1()
    name = r.name()
    return _read(r, t), name, gz


def dump(tree, path, name="", gz=True):
    out = bytearray()
    out += struct.pack(">b", tree.tag)
    nb = name.encode("utf-8")
    out += struct.pack(">H", len(nb)) + nb
    _write(out, tree)
    data = bytes(out)
    if gz:
        data = gzip.compress(data)
    Path(path).write_bytes(data)
