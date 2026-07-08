# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Windows-only StreamDock (Mirabox) plugin — "Drohack's Tools" — built on the official Python SDK example. Actions:
- **volume** — Windows master volume knob/button.
- **game_volume** — sets every app's mixer session EXCEPT an exclude list (default Discord), so game/media volume is independent of voice chat. Windows master is never touched.
- **app_volume** — one selected app's volume.
- **discord_voice** — Discord voice output volume (rotate) + deafen (press), via Discord's local RPC. Works whenever Discord runs, no audio session needed.
- **discord_mute** — Discord mic mute (press); undeafen+unmute when deafened.
- **gif** — plays gifs on a key.

There is no test suite. `tools/discord_rpc_harness.py` is a manual live test for the Discord RPC layer (run with your own Discord app client_id/secret).

## Commands

```powershell
# Setup (once)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Build the plugin exe (output: dist/DrohackPlugin.exe)
pyinstaller main.spec
```

Deploy: copy `dist/DrohackPlugin.exe` into `com.drohack.streamdock.tools.sdPlugin/`, then copy that whole folder to `%APPDATA%\HotSpot\StreamDock\plugins\`, and restart StreamDock.

The plugin cannot be run standalone — StreamDock launches the exe with `-port -pluginUUID -registerEvent -info` args and the plugin connects back over WebSocket. Debug via the log file: `logs/plugin.log` (next to the repo root in dev, next to the exe when deployed).

## Architecture

Two halves that ship together in the `com.drohack.streamdock.tools.sdPlugin/` bundle:

1. **Python backend** (`main.py`, `src/`) — compiled to `DrohackPlugin.exe` with PyInstaller.
2. **Plugin bundle** (`com.drohack.streamdock.tools.sdPlugin/`) — `manifest.json` (declares actions/UUIDs), per-action HTML/JS property inspectors, and static assets. The JS runs inside StreamDock's webview, not in Python.

### Backend event flow

- `src/core/plugin.py` — `Plugin` owns the WebSocket to StreamDock. On `willAppear` it creates one `Action` instance per button context via `ActionFactory`; all later events (`keyUp`, `dialRotate`, `didReceiveSettings`, `sendToPlugin`, …) are dispatched to that instance by duck-typed handler names (`on_key_up`, `on_dial_rotate`, `on_send_to_plugin`, …) — handlers are optional, checked with `hasattr`.
- `src/core/action_factory.py` — at import time it scans `src/actions/*.py` and registers each `Action` subclass under its **module filename** (lowercased). The registry key is matched against the **last dot-segment of the action UUID** from the manifest, so `com.drohack.streamdock.tools.gif` → `src/actions/gif.py`. Filename and UUID suffix must match exactly.
- `src/core/action.py` — base class with the outbound API (`set_title`, `set_image` (base64 data URL), `set_state`, `set_settings`, `send_to_property_inspector`, …).
- `src/core/timer.py` — single shared background thread; `plugin.timer.set_interval(uuid, ms, callback)` / `clear_interval(uuid)`. Actions use per-context uuids (e.g. `f'app_volume_update_{context}'`) and must clear them in `on_will_disappear`. **This thread calls `CoInitialize()` at startup** — all COM audio calls made from timer callbacks (volume/app_volume/game_volume) run here, and COM must be initialized per-thread.
- `src/core/audio_sessions.py` — shared `get_all_sessions(force=False)` with a 1s TTL cache (COM enumeration is expensive; caching avoids per-tick lag). Used by app_volume and game_volume.

### Shared state across action instances

Two features share one state object across all their key instances rather than storing per-context settings (multiple instances would otherwise diverge/fight):
- **game_volume** uses a module-level `_GameVolumeController` singleton (`get_controller()`): one level/mute/exclude, one 200ms enforcement loop, all keys render from it and forward input to it. Level persists in **global settings** under the `game_volume` key.
- **discord_voice/discord_mute** share `src/core/discord_rpc.py`'s `DiscordRPC` singleton (`get_discord_rpc(plugin)`) via `acquire(listener)`/`release(listener)`.

Global settings are the cross-instance/cross-action store (`plugin.get_global_settings()` / `set_global_settings()`). `set_global_settings` **replaces** the whole payload, so always merge into `dict(plugin.global_settings)` before writing (both the discord and game_volume keys live there). Note `plugin.py` never fetches global settings on its own — the first consumer must call `get_global_settings()`.

### Discord RPC (`src/core/discord_rpc.py`)

Talks to the local Discord client over the named pipe `\\.\pipe\discord-ipc-N` (8-byte LE header + JSON frames; commands `GET/SET_VOICE_SETTINGS`, `SUBSCRIBE VOICE_SETTINGS_UPDATE`; OAuth2 scopes `rpc rpc.voice.read rpc.voice.write`). Key points:
- **All pipe I/O is on ONE `io` thread using `win32file` + `PeekNamedPipe` polling.** A synchronous Windows pipe handle serializes I/O — a blocking `ReadFile` stalls every `WriteFile` — so a blocking-reader-thread design deadlocks. Never reintroduce blocking reads; enqueue outgoing frames and poll for incoming.
- Manager thread runs the connect/auth state machine; `request()` blocks on a reply the io thread resolves (safe: manager ≠ io thread).
- Voice output volume is Discord's native 0–200 (100 = normal, >100 = boost). Setup requires the user's own Discord app (client_id/secret, redirect `http://localhost`); tokens persist in global settings and auto-refresh. Only ONE app may write voice settings at a time.
- Faces: `discord_faces.py` composites the authentic Discord state icons in `discord_icons.py` (base64-embedded blurple/red mic/deafen glyphs) as a volume gauge.

### Property inspectors

`propertyInspector/<action>/index.html` + `index.js`, sharing `static/action.js` which provides the `$websocket` global (`saveData`, `sendToPlugin`, `setGlobalSettings`) and expects a `$propEvent` object of handlers (`didReceiveSettings`, `sendToPropertyInspector`, …). PI ↔ backend messaging: JS `sendToPlugin` → Python `on_send_to_plugin(payload)`; Python `send_to_property_inspector(payload)` → JS `$propEvent.sendToPropertyInspector(data)`.

### Adding a new action — full checklist

1. `src/actions/<name>.py` with an `Action` subclass (auto-registered by filename).
2. `manifest.json`: new entry in `Actions` with `UUID` ending `.<name>` and a `PropertyInspectorPath`.
3. `propertyInspector/<name>/index.html` + `index.js`.
4. New third-party imports → add to `requirements.txt` **and** to `hiddenimports` in `main.spec` — `action_factory` loads action modules via `importlib`, so PyInstaller's static analysis misses anything imported only from `src/actions/` and silently omits it from the exe.
5. Rebuild (`pyinstaller main.spec`) and redeploy.

### Frozen-vs-dev path handling

Code distinguishes environments with `getattr(sys, 'frozen', False)`. Bundled Python sources unpack to `sys._MEIPASS`; runtime assets that live in the plugin folder (e.g. gifs in `static/gifs/` for the Gif action) are resolved relative to `os.path.dirname(sys.executable)` — i.e. next to the exe inside the deployed `.sdPlugin` folder. Follow the same pattern for any new file access.

### Windows specifics

Audio actions use pycaw/comtypes (COM): call `CoInitialize()` in the action's `__init__` (see `app_volume.py`); the timer thread also `CoInitialize()`s itself for callbacks. App icons are extracted via raw ctypes `user32`/`gdi32` calls. The Discord RPC pipe uses `pywin32` (`win32file`/`win32pipe`). Everything volume-related is Windows-only by design.

**PyInstaller gotchas (learned the hard way):** stdlib/3rd-party modules only reached through dynamically-imported action code are invisible to PyInstaller's analysis and get silently omitted, causing runtime `ModuleNotFoundError`/`ImportError`. Anything new must go in `hiddenimports` in `main.spec` — this already bit `uuid`, `PIL.ImageEnhance`, `PIL.ImageFont`, `win32file`, `win32pipe`.

## Repo quirks

- `com.mirabox.streamdock.time.sdPlugin/` at the repo root is the untracked upstream SDK example — ignore it (git-ignored via a root-anchored `/com.mirabox...` rule).
- `vendor/` holds patches to *other* Mirabox plugins (weather, Time Options) that are NOT part of this plugin — each as patched file + `.orig` + `.patch`. They live installed under `%APPDATA%\HotSpot\StreamDock\plugins\` and a vendor update reverts them; `vendor/README.md` has re-apply steps. Don't confuse the root `com.mirabox.streamdock.time.sdPlugin/` (SDK demo) with `vendor/com.mirabox.streamdock.time.sdPlugin/` (the real patched Time Options plugin).
- `com.drohack.streamdock.tools.sdPlugin/DrohackPlugin.exe` is a build artifact committed into the bundle; the source of truth is `dist/` after a rebuild.
- StreamDock SDK event reference: https://sdk.key123.vip/en/guide/events-received.html (see also `propertyInspector/readme.md` for sdpi HTML snippets).
