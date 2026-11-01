"""Bounded request traces, without photos, credentials or provider payloads."""
from contextvars import ContextVar
from datetime import datetime, timezone
import uuid
import logging
from copy import deepcopy

_current = ContextVar('caltra_trace', default=None)

def record(stage, **details):
    events = _current.get()
    if events is not None and len(events) < 100:
        events.append(deepcopy({'stage': stage, **details}))

def capture(store, kind, inputs, operation):
    events = []
    token = _current.set(events)
    entry = {'id': str(uuid.uuid4()), 'at': datetime.now(timezone.utc).isoformat(),
             'kind': kind, 'input': deepcopy(inputs), 'steps': events}
    try:
        result = operation()
        entry['result'] = result
        return result
    except Exception as exc:
        entry['errorType'] = type(exc).__name__
        raise
    finally:
        _current.reset(token)
        try:
            store.save_diagnostic(entry)
        except Exception:
            # A trace failure must not turn a successful meal save into an error.
            logging.getLogger(__name__).warning('Could not persist Caltra diagnostic record')
