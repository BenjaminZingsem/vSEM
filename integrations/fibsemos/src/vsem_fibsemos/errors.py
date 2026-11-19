"""Failures carry observable outcomes, never credentials or private diagnostics."""


class ProtocolError(RuntimeError):
    pass


class AuthorityError(RuntimeError):
    pass


class QualificationRequired(RuntimeError):
    pass


class AdmissionUnknown(RuntimeError):
    """A POST may have reached the instrument. Do not resubmit it."""


class OperationFailure(RuntimeError):
    def __init__(self, receipt):
        self.receipt = dict(receipt)
        super().__init__("Operation did not complete: " + receipt['status'])


class PendingOutcome(TimeoutError):
    def __init__(self, operation_id):
        self.operation_id = operation_id
        super().__init__("Outcome pending; reconcile the known operation before retry")


class HTTPFailure(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__("Instrument HTTP status " + str(status))
