"""Shared TTL-cached access to Windows audio sessions.

AudioUtilities.GetAllSessions() is an expensive COM enumeration; calling it
per dial tick (or per 300ms timer tick) causes lag and transient COM failures
under load. Same idea as the endpoint-interface cache in volume.py, applied
to session enumeration.
"""

import os
import threading
import time

from pycaw.pycaw import AudioUtilities

from .logger import Logger

SESSIONS_TTL = 1.0  # seconds

_lock = threading.Lock()
_sessions = []
_ts = 0.0


def get_all_sessions(force=False):
    """Return cached audio sessions, re-enumerating if stale or forced."""
    global _sessions, _ts
    now = time.monotonic()
    with _lock:
        if force or now - _ts > SESSIONS_TTL:
            try:
                _sessions = AudioUtilities.GetAllSessions()
                _ts = now
            except Exception as e:
                Logger.error(f"[AudioSessions] GetAllSessions failed: {e}")
                _sessions = []
                _ts = 0.0
        return list(_sessions)


def sessions_for_process(names, force=False):
    """Sessions whose process basename is in `names` (case-insensitive set)."""
    wanted = {n.lower() for n in names}
    matched = []
    for s in get_all_sessions(force):
        try:
            if s.Process and os.path.basename(s.Process.name()).lower() in wanted:
                matched.append(s)
        except Exception:
            continue
    return matched


def sessions_excluding(names, force=False):
    """Sessions whose process basename is NOT in `names` (case-insensitive).
    Sessions without a process (system sounds) are included."""
    excluded = {n.lower() for n in names}
    matched = []
    for s in get_all_sessions(force):
        try:
            if s.Process and os.path.basename(s.Process.name()).lower() in excluded:
                continue
            matched.append(s)
        except Exception:
            continue
    return matched
