"""Game Volume: controls every app's mixer session EXCEPT an exclude list
(default: Discord), so game/media volume is independent of voice chat.

Discord carve-out: Discord renders voice from its renderer process but plays
everything else (chat videos, pings, UI beeps) through a separate Chromium
audio-service session — so only the voice session is excluded and the media
session follows game volume like any other app (see VOICE_SPLIT_APPS in
audio_sessions.py). If the process layout can't be identified, all Discord
sessions stay excluded (voice-safe fallback).

All Game Volume keys (knob, buttons) share ONE level via a module-level
controller — otherwise multiple instances would each store and re-assert their
own level every tick and fight each other. The controller owns a single
enforcement loop; absolute mode means newly launched apps conform within a
blink. Windows master volume is never touched. Level persists in the plugin's
global settings so it survives restarts and is identical on every key.
"""

import base64
import io
import os
import threading

from PIL import Image, ImageDraw
from comtypes import CoInitialize, CoUninitialize

from src.core.action import Action
from src.core.logger import Logger
from src.core.audio_sessions import sessions_excluding, get_all_sessions, is_audio_service

DEFAULT_EXCLUDE = ["Discord.exe"]


class _GameVolumeController:
    """Process-wide shared game-volume state + enforcement (singleton)."""

    STEP = 5

    def __init__(self):
        self.level = 50
        self.muted = False
        self.exclude = list(DEFAULT_EXCLUDE)
        self._listeners = []          # render callbacks: cb(level, muted)
        self._lock = threading.RLock()
        self._plugin = None
        self._timer_on = False
        self._loaded = False
        self._dirty = False

    # ------------------------------------------------------- lifecycle

    def attach(self, action):
        with self._lock:
            self._plugin = action.plugin
            if action.render not in self._listeners:
                self._listeners.append(action.render)
            first_load = not self._loaded
            self._loaded = True
            if not self._timer_on:
                self._timer_on = True
                action.plugin.timer.set_interval("game_volume_enforce", 200, self._tick)
        if first_load:
            try:
                action.plugin.get_global_settings()  # load persisted level
            except Exception as e:
                Logger.error(f"[GameVolume] get_global_settings failed: {e}")

    def detach(self, action):
        with self._lock:
            if action.render in self._listeners:
                self._listeners.remove(action.render)
            if not self._listeners and self._timer_on and self._plugin:
                self._plugin.timer.clear_interval("game_volume_enforce")
                self._timer_on = False

    # ------------------------------------------------------------ input

    def set_level_delta(self, ticks):
        with self._lock:
            self.level = max(0, min(100, self.level + ticks * self.STEP))
            self._dirty = True
        self.apply()
        self._notify()

    def toggle_mute(self):
        with self._lock:
            self.muted = not self.muted
            self._dirty = True
        self.apply()
        self._notify()

    def set_exclude(self, exclude):
        with self._lock:
            self.exclude = exclude or list(DEFAULT_EXCLUDE)
            self._dirty = True
        self.apply(force=True)
        self._notify()

    def load(self, settings):
        gv = (settings or {}).get("game_volume") or {}
        if not gv:
            return
        with self._lock:
            new = (int(gv.get("level", self.level)),
                   bool(gv.get("muted", self.muted)),
                   gv.get("exclude") or self.exclude)
            if new == (self.level, self.muted, self.exclude):
                return  # our own persist echoing back — no-op
            self.level, self.muted, self.exclude = new
        self.apply(force=True)
        self._notify()

    def snapshot(self):
        with self._lock:
            return self.level, self.muted, list(self.exclude)

    # ------------------------------------------------------- enforcement

    def _tick(self):
        self.apply()
        self._notify()
        if self._dirty:
            self._persist()

    def apply(self, force=False):
        """Set every non-excluded session to the shared level/mute. Retries
        once with fresh enumeration so a stale session doesn't drop a change."""
        with self._lock:
            level, muted, exclude = self.level, self.muted, list(self.exclude)
        for attempt in range(2):
            try:
                sessions = sessions_excluding(exclude, force=force or attempt > 0)
                if force:
                    names = []
                    for s in sessions:
                        try:
                            if s.Process:
                                name = os.path.basename(s.Process.name())
                                if is_audio_service(s):
                                    name += "(media)"
                                names.append(name)
                            else:
                                names.append("system")
                        except Exception:
                            names.append("?")
                    Logger.info(f"[GameVolume] applying level={level} muted={muted} to {len(sessions)} sessions: {names}")
                for s in sessions:
                    try:
                        vol = s.SimpleAudioVolume
                        if abs(vol.GetMasterVolume() - level / 100.0) > 0.004:
                            vol.SetMasterVolume(level / 100.0, None)
                        if bool(vol.GetMute()) != muted:
                            vol.SetMute(1 if muted else 0, None)
                    except Exception:
                        continue  # session vanished mid-iteration
                return
            except Exception as e:
                if attempt == 0:
                    Logger.warning(f"[GameVolume] apply retrying after: {e}")
                else:
                    Logger.error(f"[GameVolume] Exception in apply: {e}")

    def _persist(self):
        with self._lock:
            gv = {"level": self.level, "muted": self.muted, "exclude": list(self.exclude)}
            self._dirty = False
            plugin = self._plugin
        if not plugin:
            return
        try:
            merged = dict(plugin.global_settings or {})
            merged["game_volume"] = gv
            plugin.set_global_settings(merged)  # merge — must not clobber discord key
        except Exception as e:
            Logger.error(f"[GameVolume] failed to persist: {e}")

    def _notify(self):
        with self._lock:
            listeners = list(self._listeners)
            level, muted = self.level, self.muted
        for cb in listeners:
            try:
                cb(level, muted)
            except Exception as e:
                Logger.error(f"[GameVolume] listener error: {e}")


_controller = None
_controller_lock = threading.Lock()


def get_controller():
    global _controller
    with _controller_lock:
        if _controller is None:
            _controller = _GameVolumeController()
        return _controller


class GameVolume(Action):
    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)
        CoInitialize()
        self._last_state = None
        self.controller = get_controller()
        self.controller.attach(self)
        level, muted, _ = self.controller.snapshot()
        self.render(level, muted)
        Logger.info(f"[GameVolume] Initialized with context {context}")

    def __del__(self):
        try:
            CoUninitialize()
        except Exception:
            pass

    # ------------------------------------------------------------- display

    def generate_volume_image(self, volume_percent, is_muted=False):
        """Same look as the master Volume action: bottom-up bar, red if muted."""
        width, height = 72, 72
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        if volume_percent > 0:
            fill_height = int((volume_percent / 100) * height)
            fill_color = (255, 0, 0, 255) if is_muted else (0, 255, 0, 255)
            draw.rectangle([0, height - fill_height, width, height], fill=fill_color)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()

    def render(self, level, muted):
        """Controller listener — every key renders the same shared level."""
        state = (level, muted)
        if state == self._last_state:
            return
        self._last_state = state
        if muted:
            display = "MUTE"
        elif level == 100:
            display = "MAX"
        elif level < 10:
            display = f"0{level}"
        else:
            display = f"{level}"
        self.set_title(display)
        self.set_image(self.generate_volume_image(level, muted))

    # -------------------------------------------------------------- events

    def on_dial_rotate(self, payload: dict):
        ticks = payload.get("ticks", 0)
        if ticks:
            self.controller.set_level_delta(ticks)

    def on_dial_down(self, payload: dict):
        self.controller.toggle_mute()

    def on_key_down(self, payload: dict):
        self.controller.toggle_mute()

    # ------------------------------------------------- PI / settings plumbing

    def on_did_receive_global_settings(self, settings):
        self.controller.load(settings)

    def on_property_inspector_did_appear(self, data: dict):
        # seed the PI with running apps so the exclude list is pickable
        apps, seen = [], set()
        for s in get_all_sessions(force=True):
            try:
                if s.Process:
                    name = os.path.basename(s.Process.name())
                    if name.lower() not in seen:
                        apps.append({"value": name, "label": name.replace(".exe", "")})
                        seen.add(name.lower())
            except Exception:
                continue
        level, muted, exclude = self.controller.snapshot()
        self.send_to_property_inspector({
            "event": "updateGameVolume",
            "app_list": apps,
            "exclude": exclude,
            "level": level,
        })

    def on_send_to_plugin(self, payload: dict):
        if payload.get("event") == "setExclude":
            self.controller.set_exclude(payload.get("exclude") or list(DEFAULT_EXCLUDE))

    def on_will_disappear(self):
        self.controller.detach(self)
        Logger.info(f"[GameVolume] Will disappear for context {self.context}")
