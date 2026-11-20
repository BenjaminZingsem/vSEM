"""Immutable raw acquisition plus a labelled view, with no external imports."""
from dataclasses import dataclass
import hashlib

from .errors import ProtocolError
from .protocol import acquisitions, decode, integer
from .records import RawFrame, canonical


def match_final(frame, association, parameters=None):
    """Join one exact terminal cut; completion alone is insufficient."""
    if type(frame) is not RawFrame:
        raise ProtocolError('native raw frame required')
    if type(association) is not dict:
        raise ProtocolError('public association required')
    value = acquisitions(association, association.get('operation_id'), 'scan_single')
    cut, observed = value['final_cut'], frame.metadata
    if (value['receipt']['status'] != 'COMPLETED' or cut is None
            or cut['outcome'] != 'COMPLETED'):
        raise ProtocolError('successful terminal acquisition required')
    if any(observed[key] != cut[key] for key in ('image_id', 'source_id', 'cut_elapsed_ns', 'outcome')):
        raise ProtocolError('raw metadata differs from the exact final cut')
    if (observed['mode'] != 'SINGLE' or observed['terminal_reason'] != 'COMPLETED'
            or observed['completed_pixels'] != observed['width_px'] * observed['height_px']
            or observed['active_dwell_ns'] != 0
            or observed['cut_elapsed_ns'] < observed['width_px'] * observed['height_px'] * observed['dwell_ns']):
        raise ProtocolError('incomplete or unpaced single acquisition')
    if parameters is not None and any(observed[key] != parameters[key] for key in (
            'width_px', 'height_px', 'field_width_m', 'offset_x_m', 'offset_y_m', 'dwell_ns')):
        raise ProtocolError('acquired geometry/dwell differs from request')
    if (observed['pixel_pitch_m'] != observed['field_width_m']/observed['width_px']
            or observed['magnification_reference_width_m'] != .1
            or observed['magnification'] != .1/observed['field_width_m']):
        raise ProtocolError('inconsistent acquired pixel/display scale')
    return value


@dataclass(frozen=True)
class AcquisitionResult:
    raw_frame: RawFrame
    association_bytes: bytes
    view_bytes: bytes
    provenance_bytes: bytes

    def __post_init__(self):
        if any(type(value) is not bytes for value in (
                self.association_bytes, self.view_bytes, self.provenance_bytes)):
            raise ValueError('immutable acquisition bytes required')
        association = decode(self.association_bytes)
        match_final(self.raw_frame, association)
        provenance = decode(self.provenance_bytes)
        if type(provenance) is not dict:
            raise ProtocolError('closed view provenance required')
        black = integer(provenance.get('black'), 0, 2**32-1)
        white = integer(provenance.get('white'), black+1, 2**32-1)
        expected, transform = self.raw_frame.view(black, white, 16)
        if self.view_bytes != expected or provenance != transform:
            raise ProtocolError('derived image/provenance differs from raw counts')

    @classmethod
    def from_acquisition(cls, frame, association, black, white, parameters):
        value = match_final(frame, association, parameters)
        view, provenance = frame.view(black, white, 16)
        return cls(frame, canonical(value), view, canonical(provenance))

    @property
    def association(self):
        return decode(self.association_bytes)

    @property
    def view_provenance(self):
        return decode(self.provenance_bytes)

    @property
    def view_sha256(self):
        return hashlib.sha256(self.view_bytes).hexdigest()
