"""The optional launcher: start the worker when something is queued and none is alive (D-11).

Adapted from gimg@bc27219 gimg/service.py (`_Launcher`, `maybe_launch_worker`). It never imports an application: the
queue and the worker command come from outside. It never raises, so a failed launch cannot fail a request or stop the
service that calls it."""
from __future__ import annotations

import subprocess
import sys
import threading
import time

from . import i18n

RETRY_AFTER_FAILURE_S = 30.0  # a worker that exited with an error is not relaunched sooner

_lock = threading.Lock()  # one launch at a time in this process, whatever the number of launchers


class Launcher:
    """`queue`: the application's `Queue`. `command`: the worker's argv. `log_path`: the file the worker's output is
    appended to. `popen` and `clock` are there for tests."""

    def __init__(self, queue, command, *, log_path, lang=None, retry_after_s: float = RETRY_AFTER_FAILURE_S,
                 popen=subprocess.Popen, clock=time.monotonic):
        self.queue = queue
        self.command = list(command)
        self.log_path = log_path
        self.lang = lang
        self.retry_after_s = retry_after_s
        self._popen = popen
        self._clock = clock
        self.proc = None
        self.not_before = 0.0
        self.last_error = None

    def maybe_launch(self) -> bool:
        """Start the worker if something runnable is queued, the queue is not paused and no worker is alive (the
        worker lock must be known to be free: unknown means do not start). Returns whether one was launched."""
        with _lock:
            try:
                if self.proc is not None:
                    code = self.proc.poll()
                    if code is None:
                        return False  # ours is starting or running
                    self.proc = None
                    if code != 0:
                        self.not_before = self._clock() + self.retry_after_s
                if self._clock() < self.not_before:
                    return False
                if (self.queue.is_paused() or self.queue.worker_alive() is not False
                        or not self.queue.list_runnable()):
                    return False
                with open(self.log_path, "ab") as out:
                    self.proc = self._popen(self.command, stdin=subprocess.DEVNULL, stdout=out,
                                            stderr=subprocess.STDOUT, start_new_session=True)
                return True
            except Exception as exc:  # a failed launch must not fail a request or stop the service
                text = "%s: %s" % (type(exc).__name__, exc)
                if text != self.last_error:  # a periodic caller must not repeat one line for ever
                    self.last_error = text
                    try:
                        print(i18n.t("launcher.failed", self.lang, reason=text), file=sys.stderr, flush=True)
                    except Exception:
                        pass
                return False
