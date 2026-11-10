"""Bounded receipt bookkeeping over verified facts; never drives the engine."""


def raster_key(configuration):
    geometry = configuration.geometry
    return (geometry.width_px, geometry.height_px, geometry.field_width_m,
            geometry.offset_x_m, geometry.offset_y_m, configuration.dwell_ns)


class LiveOperationReceipts:
    def __init__(self):
        self.session = None
        self.active = None
        self.requested = None
        self.configure = None
        self.freeze = None

    def observe(self, fact, operations):
        """Return correlated status changes, under the service's operation lock."""
        kind, body = fact.kind, fact.body
        updates = []

        def terminal(operation):
            return operations.get(operation, {}).get('status') in (
                'COMPLETED', 'CANCELLED', 'REJECTED')

        def finish(operation, status, reason):
            if operation is not None and not terminal(operation):
                updates.append((operation, status, reason))

        def cancel_pending(reason):
            if self.configure is not None:
                finish(self.configure[0], 'CANCELLED', reason)
            finish(self.freeze, 'CANCELLED', reason)
            self.configure = self.freeze = None

        if kind == 'GEOMETRY':
            self.requested = (body[0], raster_key(body[2]))
        elif kind == 'DISPOSITION':
            operation, status, reason, command = body
            if command == 'StartCapture' and status == 'ACCEPTED':
                self.session = operation
                self.active = None
                self.requested = None
            elif command == 'ConfigureLive' and status == 'ACCEPTED':
                if self.configure is not None:
                    finish(self.configure[0], 'CANCELLED', 'SUPERSEDED')
                if self.requested is not None and self.requested[0] == operation:
                    self.configure = self.requested
                    if self.active == self.configure[1]:
                        finish(operation, 'COMPLETED', 'OK')
                        self.configure = None
                self.requested = None
            elif command == 'FreezeLive' and status == 'ACCEPTED':
                if self.freeze != operation:
                    finish(self.freeze, 'CANCELLED', 'SUPERSEDED')
                # SESSION_ENDED can precede this disposition in the same tick.
                self.freeze = None if terminal(operation) else operation
        elif kind == 'RASTER_START':
            self.session = body[4]
            self.active = raster_key(body[6])
            if self.configure is not None and self.active == self.configure[1]:
                finish(self.configure[0], 'COMPLETED', 'OK')
                self.configure = None
        elif kind == 'RASTER_END':
            self.active = None
        elif kind == 'SESSION_ENDED' and body[0] == self.session:
            reason, freeze = body[1:]
            finish(freeze, 'COMPLETED' if reason == 'COMPLETED' else 'CANCELLED', reason)
            # The live session may finish before a requested grid ever starts.
            cancel_pending(reason if reason != 'COMPLETED' else 'NOT_APPLIED')
            self.session = self.active = self.requested = None
        elif kind == 'LEASE' and body[0] is None:
            cancel_pending(body[1])
        elif kind == 'INTERLOCK':
            cancel_pending(body[0])
        return updates
