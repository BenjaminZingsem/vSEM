"""Read-only joins of verified facts and committed images; no engine decisions.

The service owns the lock. Each retained operation has constant-size references;
only the current session/raster and one pending configuration are tracked here.
Published images remain owned by the service's existing image records.
"""
from dataclasses import dataclass

from .live_operation_receipts import raster_key


@dataclass(frozen=True)
class Delivery:
    image_id: str
    source_id: str
    raster_id: str
    cut_elapsed_ns: int
    outcome: str
    ordinal: int

    def reference(self, images):
        record = images.get(self.image_id)
        if record is None:
            return None
        ready, observation = record
        if (ready.causal_raster_id, observation['source_id'],
                observation['cut_elapsed_ns'], observation['outcome']) != (
                self.raster_id, self.source_id, self.cut_elapsed_ns, self.outcome):
            return None
        return {name: getattr(self, name) for name in (
            'image_id', 'source_id', 'raster_id', 'cut_elapsed_ns', 'outcome')}


@dataclass
class Entry:
    owner: object
    command: str
    configuration: object = None
    target: object = None
    accepted: bool = False
    association: object = None
    latest: object = None
    final: object = None
    terminal: object = None


class OperationAcquisitions:
    def __init__(self):
        self.entries = {}
        self.session = self.raster = self.pending = None
        self.last_ordinal = 0

    def register(self, operation, owner, kind, value):
        command = 'lease' if kind == 'lease' else value['action']
        entry = Entry(owner, command)
        if command in ('scan_single', 'scan_live', 'configure_live'):
            p = value['parameters']
            entry.configuration = tuple(p[k] for k in (
                'width_px', 'height_px', 'field_width_m',
                'offset_x_m', 'offset_y_m', 'dwell_ns'))
        elif command == 'freeze':
            entry.target = value['parameters']['source_id']
        self.entries[operation] = entry

    def discard(self, operation):
        self.entries.pop(operation, None)

    @staticmethod
    def _bind(entry, relation, raster, at):
        entry.association = dict(relation=relation, source_id=raster['source_id'],
            raster_id=raster['raster_id'], applied_at_ns=at)

    @staticmethod
    def _terminal(entry, terminal):
        entry.terminal = terminal
        if entry.latest is not None:
            OperationAcquisitions._final(entry, entry.latest)

    @staticmethod
    def _final(entry, delivery):
        if entry.terminal == (delivery.raster_id, delivery.cut_elapsed_ns, delivery.outcome):
            entry.final = delivery

    def observe(self, fact, operations):
        # Facts reach this projection only after causal verification. Duplicate
        # or late replays cannot rewrite an earlier observed association.
        if not self.entries:
            return
        if fact.ordinal <= self.last_ordinal:
            return
        self.last_ordinal = fact.ordinal
        kind, body, at = fact.kind, fact.body, fact.event_at_ns
        if kind == 'DISPOSITION':
            operation, status, _, command = body
            entry = self.entries.get(operation)
            if entry is None or status != 'ACCEPTED' or entry.accepted:
                return
            entry.accepted = True
            if operations.get(operation, {}).get('status') in ('CANCELLED', 'REJECTED'):
                return
            if command == 'StartCapture' and operation != self.session:
                # A late admission must not erase a verified RASTER_START.
                if entry.association is None:
                    self.session, self.raster, self.pending = operation, None, None
            elif command == 'ConfigureLive':
                self.pending = operation
                raster = self.raster
                if (raster is not None and raster['mode'] == 'LIVE'
                        and raster['terminal'] is None
                        and raster['configuration'] == entry.configuration):
                    self._bind(entry, 'already_active', raster, at)
                    live = self.entries.get(self.session)
                    if live is not None and live.latest is not None and live.latest.raster_id == raster['raster_id']:
                        entry.latest = live.latest
                    self.pending = None
        elif kind == 'RASTER_START':
            raster_id, _, _, mode, operation, view, configuration, _, _ = body
            entry = self.entries.get(operation)
            expected = 'scan_live' if mode == 'LIVE' else 'scan_single'
            if entry is None or entry.command != expected:
                return
            if operations.get(operation, {}).get('status') in ('CANCELLED', 'REJECTED'):
                return
            raster = dict(raster_id=raster_id, source_id=view or raster_id,
                mode=mode, configuration=raster_key(configuration), terminal=None)
            self.session, self.raster = operation, raster
            if entry.association is None or mode == 'LIVE':
                self._bind(entry, 'live_session' if mode == 'LIVE' else 'started_single', raster, at)
            pending = self.entries.get(self.pending)
            if (pending is not None and pending.association is None
                    and operations.get(self.pending, {}).get('status') not in ('CANCELLED', 'REJECTED')
                    and mode == 'LIVE' and raster['configuration'] == pending.configuration):
                self._bind(pending, 'configuration_applied', raster, at)
                self.pending = None
        elif kind == 'RASTER_END' and self.raster is not None and body[0] == self.raster['raster_id']:
            terminal = (body[0], body[1], 'COMPLETED' if body[4] == 'COMPLETED' else 'CANCELLED')
            self.raster['terminal'] = terminal
            for entry in self.entries.values():
                if (entry.association is not None and entry.command in ('scan_single', 'configure_live')
                        and entry.association['raster_id'] == body[0]):
                    self._terminal(entry, terminal)
        elif kind == 'SESSION_ENDED' and body[0] == self.session:
            live = self.entries.get(self.session)
            if self.raster is not None and live is not None:
                terminal = self.raster['terminal']
                self._terminal(live, terminal)
                freeze = self.entries.get(body[2])
                if freeze is not None and freeze.command == 'freeze' and freeze.target == self.raster['source_id']:
                    self._bind(freeze, 'freeze_of', self.raster, at)
                    freeze.latest = live.latest
                    self._terminal(freeze, terminal)
            self.session = self.raster = self.pending = None
        elif (kind == 'LEASE' and body[0] is None) or kind == 'INTERLOCK':
            self.pending = None

    def publish(self, ready, observation):
        """Accept only the service's already-verified immutable image publication."""
        delivery = Delivery(ready.image_id, observation['source_id'], ready.causal_raster_id,
            observation['cut_elapsed_ns'], observation['outcome'], ready.numerical_ordinal)
        for entry in self.entries.values():
            association = entry.association
            if association is None or association['source_id'] != delivery.source_id:
                continue
            if (entry.command not in ('scan_live', 'freeze')
                    and association['raster_id'] != delivery.raster_id):
                continue
            if entry.latest is None or delivery.ordinal > entry.latest.ordinal:
                entry.latest = delivery
            self._final(entry, delivery)

    def projection(self, operation, owner, receipt, images):
        entry = self.entries.get(operation)
        if entry is None or entry.owner != owner:
            raise KeyError('not_found')
        return dict(protocol='vsem.operation-acquisitions.v1', operation_id=operation,
            command=entry.command, receipt=dict(receipt),
            association=None if entry.association is None else dict(entry.association),
            latest_cut=None if entry.latest is None else entry.latest.reference(images),
            final_cut=None if entry.final is None else entry.final.reference(images))
