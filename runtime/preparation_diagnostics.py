"""Bounded private failure categories. Exception text never enters records."""
import json
import os
from pathlib import Path
import secrets

from engine import human_episode_types as t


class PreparationDiagnostics:
    LIMIT = 8

    def __init__(self, directory):
        self.directory = Path(directory) / 'preparation-diagnostics'
        self.attempts = 0
        self.created = False

    def record(self, ticket, error):
        # Consume an attempt even if storage fails: no unbounded retry work.
        if self.attempts >= self.LIMIT:return
        slot = self.attempts
        self.attempts += 1
        try:
            t.exact(ticket, t.BankTicket)
            category = {
                MemoryError: 'MEMORY_ERROR', ValueError: 'VALUE_ERROR',
                TypeError: 'TYPE_ERROR', OSError: 'IO_ERROR',
                RuntimeError: 'RUNTIME_ERROR',
            }.get(type(error), 'PREPARATION_ERROR')
            payload = (json.dumps({
                'protocol': 'vsem.private.preparation-failure.v1',
                'diagnostic_id': secrets.token_hex(16), 'category': category,
                'ticket_id': ticket.job_id, 'operation_id': ticket.request_id,
            }, separators=(',', ':')) + '\n').encode('utf-8')
            if len(payload) > 1024:return
            if not self.created:
                self.directory.mkdir(mode=0o700, exist_ok=False)
                self.created = True
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
            descriptor = os.open(self.directory / ('failure-' + str(slot) + '.json'), flags, 0o600)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(payload)
        except Exception:
            # Diagnostics must not obstruct the unchanged fail-closed result.
            return

    def guard(self, prepare):
        def diagnosed(ticket):
            try:return prepare(ticket)
            except Exception as error:
                self.record(ticket, error)
                raise
        return diagnosed
