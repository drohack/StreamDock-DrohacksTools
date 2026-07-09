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

# Excluded apps whose Chromium audio-service session carries only NON-voice
# audio (chat videos, pings, UI beeps) and should therefore still be volume-
# controlled. Discord's native voice engine renders voice from its renderer
# process, bypassing the audio service — verified empirically per process via
# session peak meters. Do NOT add generic Electron apps here: in a normal
# Chromium app ALL audio flows through the audio service, so this carve-out
# would un-exclude the app entirely.
VOICE_SPLIT_APPS = {"discord.exe"}

_AUDIO_SERVICE_ARG = "--utility-sub-type=audio.mojom.AudioService"

_lock = threading.Lock()
_sessions = []
_ts = 0.0

_audio_service_cache = {}  # pid -> (create_time, bool)


def is_audio_service(session):
    """True iff the session's process is a Chromium audio-service utility
    process. cmdline() is a per-process syscall and this runs on the 200ms
    enforcement tick, so results are cached per (pid, create_time). Any
    failure (process gone, AccessDenied) returns False — the session stays
    excluded, which is the voice-safe fallback."""
    try:
        proc = session.Process
        pid = proc.pid
        created = proc.create_time()
        cached = _audio_service_cache.get(pid)
        if cached and cached[0] == created:
            return cached[1]
        result = any(_AUDIO_SERVICE_ARG in arg for arg in proc.cmdline())
        if len(_audio_service_cache) > 64:  # bound growth from dead PIDs
            _audio_service_cache.clear()
        _audio_service_cache[pid] = (created, result)
        return result
    except Exception:
        return False


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
    Sessions without a process (system sounds) are included.

    Carve-out: for VOICE_SPLIT_APPS, only the voice session is excluded — the
    app's audio-service session (videos, pings, UI sounds) is still returned."""
    excluded = {n.lower() for n in names}
    matched = []
    for s in get_all_sessions(force):
        try:
            if s.Process:
                basename = os.path.basename(s.Process.name()).lower()
                if basename in excluded and not (
                    basename in VOICE_SPLIT_APPS and is_audio_service(s)
                ):
                    continue
            matched.append(s)
        except Exception:
            continue
    return matched
