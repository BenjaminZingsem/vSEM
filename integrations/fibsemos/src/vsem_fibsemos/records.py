"""Lossless raw detector records and explicitly derived compatibility views.

No claim of calibrated electron counts, crash durability, or adversarial file
confinement. The original raw bytes and observable acquisition metadata survive.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from .errors import ProtocolError
from .protocol import decode, identity, integer, keys, real
from .units import resolution

MAGIC = b'VSEM-RAW-1\n'
MAX_METADATA = 4 * 1024 * 1024
MAX_RAW = 1024 * 1024 * 4
FIELDS = ('protocol', 'image_id', 'source_id', 'mode', 'outcome', 'terminal_reason',
          'origin_ns', 'cut_elapsed_ns', 'numerical_verified_ordinal',
          'causal_verified_ordinal', 'width_px', 'height_px', 'completed_pixels',
          'active_dwell_ns', 'dwell_ns', 'field_width_m', 'pixel_pitch_m',
          'magnification', 'magnification_reference_width_m', 'stage',
          'offset_x_m', 'offset_y_m', 'incident_pA_ns', 'parameter_segments',
          'blank_holds', 'raw_format', 'calibration_status', 'detector')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('ascii')


def validate_metadata(value):
    keys(value, FIELDS)
    if (value['protocol'] != 'vsem.core-native-image.v2' or
            value['raw_format'] != 'uint32_little_endian' or
            value['detector'] != 'SE' or value['calibration_status'] != 'generic_uncalibrated'):
        raise ValueError("unqualified image format")
    for key in ('image_id', 'source_id'):
        identity(value[key])
    if value['mode'] not in ('SINGLE', 'LIVE') or value['outcome'] not in ('ACQUIRING', 'COMPLETED', 'CANCELLED'):
        raise ValueError("unknown acquisition outcome")
    if value['terminal_reason'] is not None and (type(value['terminal_reason']) is not str or len(value['terminal_reason']) > 256):
        raise ValueError("invalid terminal reason")
    w, h = resolution(value['width_px'], value['height_px'])
    integer(value['completed_pixels'], 0, w * h)
    for key in ('origin_ns', 'cut_elapsed_ns', 'numerical_verified_ordinal', 'causal_verified_ordinal',
                'active_dwell_ns', 'dwell_ns'):
        integer(value[key])
    # Incident accounting can be unavailable after a terminal numerical fault.
    if value['incident_pA_ns'] is not None:
        integer(value['incident_pA_ns'])
    for key in ('field_width_m', 'pixel_pitch_m', 'magnification', 'magnification_reference_width_m'):
        real(value[key], 0., 1e12)
    for key in ('offset_x_m', 'offset_y_m'):
        real(value[key], -.005, .005)
    _stage(value['stage'])
    if type(value['parameter_segments']) is not list or type(value['blank_holds']) is not list:
        raise ValueError("invalid exposure history")
    for item in value['parameter_segments']:
        keys(item, ('start_elapsed_ns', 'end_elapsed_ns', 'current_pA', 'focus_offset_m',
                    'stigmator_x', 'stigmator_y', 'stage'))
        _interval(item)
        integer(item['current_pA'], 1, 1000)
        real(item['focus_offset_m'], -25e-6, 25e-6)
        real(item['stigmator_x'], -1., 1.)
        real(item['stigmator_y'], -1., 1.)
        _stage(item['stage'])
    for item in value['blank_holds']:
        keys(item, ('start_elapsed_ns', 'end_elapsed_ns'))
        _interval(item)


def _stage(value):
    keys(value, ('x_m', 'y_m', 'z_m', 'working_distance_m'))
    for key, limit in (('x_m', .025), ('y_m', .025), ('z_m', 20e-6)):
        real(value[key], -limit, limit)
    real(value['working_distance_m'], 0., 1.)


def _interval(value):
    integer(value['start_elapsed_ns'])
    integer(value['end_elapsed_ns'], value['start_elapsed_ns'])


@dataclass(frozen=True)
class RawFrame:
    """Immutable byte record. Metadata access returns a defensive copy."""
    raw: bytes
    metadata_bytes: bytes

    def __post_init__(self):
        if type(self.raw) is not bytes or type(self.metadata_bytes) is not bytes:
            raise ValueError("immutable bytes required")
        if len(self.metadata_bytes) > MAX_METADATA or len(self.raw) > MAX_RAW:
            raise ValueError("record exceeds native1024/metadata envelope")
        metadata = decode(self.metadata_bytes)
        validate_metadata(metadata)
        if len(self.raw) != metadata['width_px'] * metadata['height_px'] * 4:
            raise ValueError("incomplete raw plane")

    @classmethod
    def from_observation(cls, raw, metadata):
        return cls(raw, canonical(metadata))

    @property
    def metadata(self):
        return decode(self.metadata_bytes)

    @property
    def digest(self):
        return hashlib.sha256(self.raw).hexdigest()

    def save(self, path):
        envelope = canonical({'format': 'vsem.fibsemos.raw.v1',
                              'measurement_kind': 'simulated_SE_detector_counts_uncalibrated',
                              'raw_sha256': self.digest,
                              'metadata_sha256': hashlib.sha256(canonical(self.metadata)).hexdigest(),
                              'metadata': self.metadata})
        if len(envelope) > MAX_METADATA:
            raise ValueError("metadata envelope too large")
        # Exclusive creation; no overwrite, archive extraction, executable payload,
        # directory traversal, companion discovery or hidden filesystem reads.
        with Path(path).open('xb') as stream:
            stream.write(MAGIC + struct.pack('<Q', len(envelope)) + envelope + self.raw)

    @classmethod
    def load(cls, path):
        with Path(path).open('rb') as stream:
            if stream.read(len(MAGIC)) != MAGIC:
                raise ValueError("wrong record format")
            length_raw = stream.read(8)
            if len(length_raw) != 8:
                raise ValueError("truncated record header")
            length = struct.unpack('<Q', length_raw)[0]
            if length > MAX_METADATA:
                raise ValueError("metadata envelope too large")
            encoded = stream.read(length)
            if len(encoded) != length:
                raise ValueError("truncated metadata")
            envelope = decode(encoded)
            keys(envelope, ('format', 'measurement_kind', 'raw_sha256', 'metadata_sha256', 'metadata'))
            if (envelope['format'] != 'vsem.fibsemos.raw.v1' or
                    envelope['measurement_kind'] != 'simulated_SE_detector_counts_uncalibrated'):
                raise ValueError("unknown measurement format")
            raw = stream.read(MAX_RAW + 1)
        result = cls.from_observation(raw, envelope['metadata'])
        if result.digest != envelope['raw_sha256']:
            raise ValueError("raw digest mismatch")
        if hashlib.sha256(canonical(result.metadata)).hexdigest() != envelope['metadata_sha256']:
            raise ValueError("metadata digest mismatch")
        return result

    def view(self, black, white, bits=16):
        """Fixed linear window with exact integer round-half-up; no auto scaling."""
        integer(black, 0, 2**32 - 1)
        integer(white, black + 1, 2**32 - 1)
        if type(bits) is not int or bits not in (8, 16):
            raise ValueError("only labelled uint8/uint16 views")
        maximum, span = 2**bits - 1, white - black
        output = bytearray()
        for (count,) in struct.iter_unpack('<I', self.raw):
            clipped = min(span, max(0, count - black))
            value = (2 * clipped * maximum + span) // (2 * span)
            output.extend(struct.pack('<B' if bits == 8 else '<H', value))
        metadata = self.metadata
        transform = {'format': 'vsem.fibsemos.derived-view.v1',
                     'source_raw_sha256': self.digest,
                     'source_metadata_sha256': hashlib.sha256(canonical(metadata)).hexdigest(),
                     'source_image_id': metadata['image_id'], 'source_source_id': metadata['source_id'],
                     'width_px': metadata['width_px'], 'height_px': metadata['height_px'],
                     'dtype': 'uint8' if bits == 8 else 'uint16_little_endian',
                     'black': black, 'white': white, 'scale_numerator': maximum,
                     'scale_denominator': span, 'clipping': 'window_endpoints',
                     'rounding': 'nearest_half_up', 'orientation': 'columns_positive_x_rows_negative_y',
                     'filtering': 'none', 'processing': 'fixed_linear_window_only',
                     'raw_companion_required': True, 'lossless_counts': False,
                     'measurement_kind': 'derived_display_intensity'}
        return bytes(output), transform
