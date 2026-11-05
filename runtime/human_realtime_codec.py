"""Versioned private fixed scalar cells;closed constructors,no object restore.

Registered classes are scalar records only. Private development v4 adds exact
input/time witnesses and numerical cuts; v2/v3 and public contracts are unchanged.
"""
from dataclasses import fields
import math
import struct

from engine import human_episode_types as t
from engine.human_episode_facts import EpisodeFact, EpisodeState
from .grounded_mailbox import CELL_BYTES

from .human_realtime_records import TickBegin, TickEnd, NumericalCut

MAGIC = b'VSEMRT04'
VERSION = 4
HEADER_BYTES = 72
HEADER = struct.Struct('<8sHHI16sQQQQ8s')
CLASSES = (t.ScienceIdentity, t.EpisodeSettings, t.EpisodeGeometry, t.ScanRequest,
    t.ScanConfiguration, t.ScalarBankHandle, t.AuthorityRef, t.LeaseState,
    t.GrantAuthority, t.RenewAuthority, t.RevokeAuthority, t.StartCapture,
    t.ConfigureLive, t.SetOptics, t.MoveStage, t.SafetyStop, t.FreezeLive,
    t.BankTicket, t.BankReady, t.BankFailed, t.VerifiedAcknowledgement,
    t.EpisodeFault, t.EpisodeInputs, EpisodeFact, EpisodeState, t.MoveStageXYZ, TickBegin, TickEnd, NumericalCut)
CLASS_TAG = {cls: 16+i for i, cls in enumerate(CLASSES)}
TAG_CLASS = {value: key for key, value in CLASS_TAG.items()}
CLASS_FIELDS = {cls: tuple(field.name for field in fields(cls)) for cls in CLASSES}
TOP_LEVEL = (t.EpisodeInputs, t.BankTicket, t.BankReady, t.BankFailed,
             t.VerifiedAcknowledgement, t.EpisodeFault, EpisodeFact, EpisodeState, t.ScienceIdentity, TickBegin, TickEnd, NumericalCut)


def _encode(value, depth=0):
    if depth > 8:
        raise ValueError('scalar nesting exceeds the fixed protocol envelope')
    cls = type(value)
    if value is None:
        return b'\x00'
    if cls is bool:
        return b'\x01'+bytes([int(value)])
    if cls is int:
        if not 0 <= value < 2**64:
            raise ValueError('unsigned exact scalar integer required')
        return b'\x02'+struct.pack('<Q', value)
    if cls is float:
        if not math.isfinite(value):
            raise ValueError('finite binary64 scalar required')
        return b'\x03'+struct.pack('<d', value)
    if cls is str:
        t.identity(value)
        raw = value.encode('ascii')
        return b'\x04'+struct.pack('<H', len(raw))+raw+bytes(64-len(raw))
    if cls is tuple:
        if len(value) > 32:
            raise ValueError('fixed scalar tuple envelope exceeded')
        return b'\x05'+bytes([len(value)])+b''.join(_encode(item, depth+1) for item in value)
    if cls in CLASS_TAG:
        return bytes([CLASS_TAG[cls]])+b''.join(_encode(getattr(value, name), depth+1) for name in CLASS_FIELDS[cls])
    raise ValueError('unregistered scalar type/graph/body is forbidden')


class _Reader:
    def __init__(self, raw):
        self.raw, self.offset = raw, 0

    def take(self, count):
        end = self.offset+count
        if end > len(self.raw):
            raise ValueError('truncated private scalar body')
        result = self.raw[self.offset:end]
        self.offset = end
        return result

    def value(self, depth=0):
        if depth > 8:
            raise ValueError('scalar nesting exceeds the fixed protocol envelope')
        tag = self.take(1)[0]
        if tag == 0:
            return None
        if tag == 1:
            value = self.take(1)[0]
            if value > 1:
                raise ValueError('noncanonical scalar bool')
            return bool(value)
        if tag == 2:
            return struct.unpack('<Q', self.take(8))[0]
        if tag == 3:
            value = struct.unpack('<d', self.take(8))[0]
            if not math.isfinite(value):
                raise ValueError('nonfinite scalar body')
            return value
        if tag == 4:
            count = struct.unpack('<H', self.take(2))[0]
            raw = self.take(64)
            if not 1 <= count <= 64 or any(raw[count:]):
                raise ValueError('noncanonical bounded ASCII padding')
            try:
                value = raw[:count].decode('ascii')
            except UnicodeDecodeError as exc:
                raise ValueError('non-ASCII private identity') from exc
            return t.identity(value)
        if tag == 5:
            count = self.take(1)[0]
            if count > 32:
                raise ValueError('oversized scalar tuple')
            return tuple(self.value(depth+1) for _ in range(count))
        cls = TAG_CLASS.get(tag)
        if cls is None:
            raise ValueError('unknown private scalar type tag')
        values = [self.value(depth+1) for _ in CLASS_FIELDS[cls]]
        return cls(*values)


def encode_cell(value, nonce, producer_sequence):
    if type(value) not in TOP_LEVEL or type(nonce) is not bytes or len(nonce) != 16:
        raise ValueError('closed top-level record and private16-byte episode nonce required')
    t.integer(producer_sequence, 1)
    payload = _encode(value)
    if len(payload) > CELL_BYTES-HEADER_BYTES:
        raise ValueError('fixed private cell payload exceeded')
    ordinal = predecessor = observed = 0
    if type(value) is EpisodeFact:
        ordinal, predecessor, observed = value.ordinal, value.predecessor, value.event_at_ns
    elif type(value) is EpisodeState:
        ordinal, observed = value.last_ordinal, value.now_ns
    header = HEADER.pack(MAGIC, VERSION, CLASS_TAG[type(value)], len(payload), nonce,
        producer_sequence, producer_sequence-1, ordinal, observed, bytes(8))
    # Header predecessor at40 is the SPSC sequence predecessor;the merged
    # fact predecessor is carried explicitly in its closed record body.
    return header+payload+bytes(CELL_BYTES-HEADER_BYTES-len(payload))


def decode_cell(cell, nonce, expected_sequence):
    if type(cell) is not bytes or len(cell) != CELL_BYTES or type(nonce) is not bytes or len(nonce) != 16:
        raise ValueError('exact fixed private cell and nonce required')
    t.integer(expected_sequence, 1)
    magic, version, tag, count, received_nonce, sequence, predecessor, ordinal, observed, reserved = HEADER.unpack_from(cell)
    if (magic != MAGIC or version != VERSION or received_nonce != nonce or sequence != expected_sequence
            or predecessor != sequence-1 or any(reserved) or not 1 <= count <= CELL_BYTES-HEADER_BYTES
            or any(cell[HEADER_BYTES+count:])):
        raise ValueError('noncanonical/foreign/missing private cell sequence')
    reader = _Reader(cell[HEADER_BYTES:HEADER_BYTES+count])
    value = reader.value()
    if reader.offset != count or type(value) not in TOP_LEVEL or CLASS_TAG[type(value)] != tag:
        raise ValueError('private cell tag/body/length mismatch')
    if _encode(value) != cell[HEADER_BYTES:HEADER_BYTES+count]:
        raise ValueError('noncanonical coerced private scalar representation')
    if type(value) is EpisodeFact:
        if (ordinal, observed) != (value.ordinal, value.event_at_ns):
            raise ValueError('private fact source header mismatch')
    elif type(value) is EpisodeState:
        if (ordinal, observed) != (value.last_ordinal, value.now_ns):
            raise ValueError('private state source header mismatch')
    elif ordinal != 0 or observed != 0:
        raise ValueError('unused private input source header must be zero')
    return value

