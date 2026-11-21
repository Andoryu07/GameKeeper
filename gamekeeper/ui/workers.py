"""Run slow work (network, disk) off the UI thread."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_alive: set = set()   # keep signal objects alive until their job finishes


class _Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, int)


class _Job(QRunnable):
    def __init__(self, fn, signals: _Signals, with_progress: bool):
        super().__init__()
        self.fn, self.signals, self.with_progress = fn, signals, with_progress

    def run(self):
        try:
            if self.with_progress:
                result = self.fn(lambda d, t: self.signals.progress.emit(d, t))
            else:
                result = self.fn()
        except Exception as e:  # noqa: BLE001 - shown to the user
            traceback.print_exc()
            self.signals.error.emit(str(e) or e.__class__.__name__)
        else:
            self.signals.done.emit(result)


def run_async(fn, on_done=None, on_error=None, on_progress=None):
    """Run ``fn()`` in a worker thread; callbacks run on the UI thread.

    If ``on_progress`` is given, ``fn`` receives a ``progress(done, total)``
    callable as its only argument.
    """
    sig = _Signals()
    _alive.add(sig)

    def finish(*_):
        _alive.discard(sig)

    if on_done:
        sig.done.connect(on_done)
    if on_error:
        sig.error.connect(on_error)
    if on_progress:
        sig.progress.connect(on_progress)
    sig.done.connect(finish)
    sig.error.connect(finish)
    QThreadPool.globalInstance().start(_Job(fn, sig, on_progress is not None))
