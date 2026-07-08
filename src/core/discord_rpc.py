r"""Discord local RPC client (named pipe IPC).

Talks to the running Discord desktop client over \\.\pipe\discord-ipc-N to
read/write voice settings (output volume, deafen, mute) regardless of whether
Discord currently has an audio session in the Windows mixer.

Design notes:
- One process-wide singleton shared by all Discord action instances
  (get_discord_rpc). Actions acquire()/release() with a listener callback.
- Windows named pipes opened for synchronous I/O serialize on the handle: a
  blocking ReadFile stalls every WriteFile on the same handle. So ALL pipe I/O
  happens on ONE io thread that polls with PeekNamedPipe (never blocks on an
  empty read) and drains an outgoing queue — writes always get through.
    io thread:      writes queued frames, flushes coalesced voice patches,
                    polls+dispatches incoming frames, answers PINGs
    manager thread: connection state machine + reconnect loop; drives the
                    handshake/auth/subscribe sequence via request() (which
                    enqueues a frame and blocks on a reply the io thread
                    resolves — safe because manager != io thread)
- Dial ticks update the local snapshot optimistically and redraw instantly;
  Discord echoing our own SET back is suppressed for a short window so the
  display doesn't stutter backwards. After the window, server state wins
  (changes made in the Discord UI flow through).
- Discord only allows ONE connected app to write voice settings, and reverts
  them when that app disconnects — we re-seed from GET_VOICE_SETTINGS on
  every (re)connect.
"""

import collections
import json
import struct
import threading
import time
import uuid

import requests
import win32file
import win32pipe
import pywintypes

from .logger import Logger

TOKEN_URL = "https://discord.com/api/oauth2/token"
REDIRECT_URI = "http://localhost"
SCOPES = ["rpc", "rpc.voice.read", "rpc.voice.write"]

# Connection states
NO_CREDS = "no_creds"            # no client_id configured
NEEDS_CONNECT = "needs_connect"  # creds present, user must click Connect (authorize)
NO_DISCORD = "no_discord"        # Discord not running / pipe not found
CONNECTING = "connecting"
AWAITING_APPROVAL = "awaiting_approval"
AUTHENTICATING = "authenticating"
READY = "ready"
AUTH_FAILED = "auth_failed"

# IPC opcodes
OP_HANDSHAKE = 0
OP_FRAME = 1
OP_CLOSE = 2
OP_PING = 3
OP_PONG = 4

ECHO_SUPPRESS_S = 0.3   # ignore server echo of our own writes for this long
SEND_SPACING_S = 0.05   # min spacing between coalesced SET_VOICE_SETTINGS
IDLE_GRACE_S = 3.0      # keep connection through brief profile switches
POLL_S = 0.02           # io thread poll cadence


class DiscordRPCError(Exception):
    def __init__(self, data):
        self.data = data or {}
        self.code = self.data.get("code")
        super().__init__(f"Discord RPC error {self.code}: {self.data.get('message')}")


class DiscordRPC:
    def __init__(self, plugin):
        self.plugin = plugin
        self._lock = threading.RLock()

        self._creds = {}          # client_id/client_secret/access_token/refresh_token/expires_at/user
        self._state = NO_CREDS
        self._detail = ""
        self._voice = {"output_volume": 100.0, "input_volume": 100.0, "deaf": False, "mute": False}
        self._local_ts = {}       # field -> monotonic ts of our last optimistic write

        self._handle = None
        self._recv_buf = bytearray()
        self._outgoing = collections.deque()   # (op, payload) frames to write
        self._pending = {}        # nonce -> {'event': Event, 'msg': dict|None, 'sync': bool}
        self._pending_patch = {}
        self._last_send_ts = 0.0
        self._listeners = []
        self._refcount = 0
        self._idle_timer = None
        self._suspended = True    # no actions on screen -> stay disconnected

        self._wake = threading.Event()
        self._conn_dead = threading.Event()
        self._ready_evt = threading.Event()
        self._needs_auth = False
        self._authorize_requested = False
        self._started = False
        self._stop = False

    # ------------------------------------------------------------------ API

    def acquire(self, listener):
        with self._lock:
            if listener not in self._listeners:
                self._listeners.append(listener)
            self._refcount += 1
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None
            self._suspended = False
            if not self._started:
                self._started = True
                threading.Thread(target=self._manager_loop, daemon=True, name="discord-manager").start()
                # plugin never fetches global settings on its own; trigger it so
                # stored credentials arrive via didReceiveGlobalSettings
                try:
                    self.plugin.get_global_settings()
                except Exception as e:
                    Logger.error(f"[DiscordRPC] get_global_settings failed: {e}")
        self._wake.set()

    def release(self, listener):
        with self._lock:
            if listener in self._listeners:
                self._listeners.remove(listener)
            self._refcount = max(0, self._refcount - 1)
            if self._refcount == 0 and not self._idle_timer:
                self._idle_timer = threading.Timer(IDLE_GRACE_S, self._idle_shutdown)
                self._idle_timer.daemon = True
                self._idle_timer.start()

    def _idle_shutdown(self):
        with self._lock:
            self._idle_timer = None
            if self._refcount > 0:
                return
            self._suspended = True
        Logger.info("[DiscordRPC] No Discord actions on screen; disconnecting")
        self._kill_pipe()
        self._wake.set()

    def update_credentials(self, creds: dict):
        """Called with the `discord` key of global settings whenever they arrive."""
        creds = creds or {}
        with self._lock:
            if creds == self._creds:
                return
            had_id = bool(self._creds.get("client_id"))
            self._creds = dict(creds)
        if creds.get("client_id") and not had_id:
            Logger.info("[DiscordRPC] Credentials received")
        self._kill_pipe()  # reconnect with the received credentials/tokens
        self._wake.set()

    def save_credentials(self, client_id: str, client_secret: str):
        """From the PI: store new app credentials (resets tokens if id changed)."""
        with self._lock:
            if self._creds.get("client_id") != client_id:
                self._creds = {}
            self._creds["client_id"] = client_id.strip()
            self._creds["client_secret"] = client_secret.strip()
        self._persist_creds()
        self._kill_pipe()  # reconnect under the new client_id
        self._wake.set()

    def begin_authorize(self):
        with self._lock:
            self._authorize_requested = True
        self._kill_pipe()  # restart the connect sequence with authorize enabled
        self._wake.set()

    def forget(self):
        with self._lock:
            for k in ("access_token", "refresh_token", "expires_at", "user"):
                self._creds.pop(k, None)
        self._persist_creds()
        self._kill_pipe()
        self._wake.set()

    def voice_snapshot(self):
        with self._lock:
            return dict(self._voice)

    @property
    def state(self):
        return self._state

    def status(self):
        with self._lock:
            return {
                "state": self._state,
                "detail": self._detail,
                "user": (self._creds.get("user") or {}),
                "has_creds": bool(self._creds.get("client_id") and self._creds.get("client_secret")),
                "voice": dict(self._voice),
            }

    def set_local_voice(self, fields: dict):
        """Optimistic local update (display responds instantly)."""
        now = time.monotonic()
        with self._lock:
            for k, v in fields.items():
                self._voice[k] = v
                self._local_ts[k] = now
        self._notify()

    def queue_voice_patch(self, patch: dict):
        """Merge a partial SET_VOICE_SETTINGS payload; the io thread coalesces
        bursts and always delivers the final value."""
        with self._lock:
            for k, v in patch.items():
                if isinstance(v, dict):
                    self._pending_patch.setdefault(k, {}).update(v)
                else:
                    self._pending_patch[k] = v

    # ------------------------------------------------------------ pipe I/O
    # (all of these run on the io thread, except _enqueue and _kill_pipe)

    def _open_pipe(self):
        for i in range(10):
            try:
                return win32file.CreateFile(
                    rf"\\.\pipe\discord-ipc-{i}",
                    win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                    0, None, win32file.OPEN_EXISTING, 0, None)
            except pywintypes.error:
                continue
        return None

    def _enqueue(self, op: int, payload: dict):
        self._outgoing.append((op, payload))

    def _drain_outgoing(self):
        while self._outgoing:
            op, payload = self._outgoing.popleft()
            data = json.dumps(payload).encode("utf-8")
            win32file.WriteFile(self._handle, struct.pack("<II", op, len(data)) + data)

    def _poll_incoming(self):
        """Read whatever bytes are available (non-blocking) and dispatch any
        complete frames."""
        try:
            _, avail, _ = win32pipe.PeekNamedPipe(self._handle, 0)
        except pywintypes.error as e:
            raise ConnectionError(f"peek failed: {e}")
        if avail:
            _, chunk = win32file.ReadFile(self._handle, avail)
            self._recv_buf += chunk
        while len(self._recv_buf) >= 8:
            op, length = struct.unpack("<II", self._recv_buf[:8])
            if len(self._recv_buf) < 8 + length:
                break
            body = bytes(self._recv_buf[8:8 + length])
            del self._recv_buf[:8 + length]
            self._dispatch(op, json.loads(body.decode("utf-8")))

    def _kill_pipe(self):
        with self._lock:
            handle, self._handle = self._handle, None
        if handle:
            try:
                win32file.CloseHandle(handle)
            except Exception:
                pass
        self._conn_dead.set()

    # ------------------------------------------------------- request layer

    def request(self, cmd: str, args: dict = None, evt: str = None, timeout: float = 5.0) -> dict:
        """Enqueue a command and block for its reply (call from manager thread
        only — never the io thread)."""
        nonce = str(uuid.uuid4())
        waiter = {"event": threading.Event(), "msg": None, "sync": True}
        with self._lock:
            self._pending[nonce] = waiter
        payload = {"cmd": cmd, "args": args or {}, "nonce": nonce}
        if evt:
            payload["evt"] = evt
        self._enqueue(OP_FRAME, payload)
        try:
            if not waiter["event"].wait(timeout):
                raise TimeoutError(f"Discord RPC timeout for {cmd}")
        finally:
            with self._lock:
                self._pending.pop(nonce, None)
        msg = waiter["msg"]
        if msg is None:
            raise ConnectionError(f"connection lost during {cmd}")
        if msg.get("evt") == "ERROR":
            raise DiscordRPCError(msg.get("data"))
        return msg.get("data") or {}

    def send_async(self, cmd: str, args: dict):
        """Fire-and-forget; errors are logged when replies arrive."""
        nonce = str(uuid.uuid4())
        with self._lock:
            self._pending[nonce] = {"event": None, "msg": None, "sync": False}
        self._enqueue(OP_FRAME, {"cmd": cmd, "args": args or {}, "nonce": nonce})

    # ------------------------------------------------------------- threads

    def _io_loop(self):
        """Owns the pipe handle for its lifetime; the only thread that touches
        it. Exits (and sets _conn_dead) on any pipe error."""
        try:
            while not self._conn_dead.is_set() and self._handle is not None:
                self._drain_outgoing()
                self._flush_voice_patch()
                self._poll_incoming()
                time.sleep(POLL_S)
        except (pywintypes.error, ConnectionError, OSError) as e:
            if self._handle is not None:  # unexpected (not our own shutdown)
                Logger.info(f"[DiscordRPC] Connection lost: {e}")
        finally:
            with self._lock:
                pending, self._pending = self._pending, {}
            for waiter in pending.values():
                if waiter["sync"] and waiter["event"]:
                    waiter["event"].set()
            self._conn_dead.set()

    def _flush_voice_patch(self):
        now = time.monotonic()
        with self._lock:
            if not self._pending_patch or now - self._last_send_ts < SEND_SPACING_S:
                return
            if self._state != READY:
                return
            patch, self._pending_patch = self._pending_patch, {}
            self._last_send_ts = now
        self.send_async("SET_VOICE_SETTINGS", patch)

    def _dispatch(self, op: int, msg: dict):
        if op == OP_PING:
            self._enqueue(OP_PONG, msg)
            return
        if op == OP_CLOSE:
            raise ConnectionError(f"Discord closed connection: {msg}")
        if op != OP_FRAME:
            return

        cmd = msg.get("cmd")
        evt = msg.get("evt")
        nonce = msg.get("nonce")

        if cmd == "DISPATCH" and evt == "READY":
            self._ready_evt.set()
            return
        if cmd == "DISPATCH" and evt == "VOICE_SETTINGS_UPDATE":
            self._apply_server_voice(msg.get("data") or {})
            return

        if nonce:
            with self._lock:
                waiter = self._pending.pop(nonce, None)
            if waiter is None:
                return
            if waiter["sync"]:
                waiter["msg"] = msg
                waiter["event"].set()
            elif evt == "ERROR":
                data = msg.get("data") or {}
                Logger.warning(f"[DiscordRPC] {cmd} rejected: {data}")
                if data.get("code") == 4006:
                    self._needs_auth = True
                    self._conn_dead.set()  # trigger reconnect+reauth
                else:
                    self._set_detail("Another app may be controlling Discord voice settings")
                    self._enqueue(OP_FRAME, {"cmd": "GET_VOICE_SETTINGS", "args": {},
                                             "nonce": str(uuid.uuid4())})
            elif cmd in ("SET_VOICE_SETTINGS", "GET_VOICE_SETTINGS"):
                # success replies carry the full settings; treat like an update
                self._apply_server_voice(msg.get("data") or {})

    def _manager_loop(self):
        while not self._stop:
            wait_s = None  # default: block until woken
            try:
                with self._lock:
                    suspended = self._suspended
                    creds = dict(self._creds)
                    authorize = self._authorize_requested
                if suspended:
                    pass  # wait for acquire()
                elif not (creds.get("client_id") and creds.get("client_secret")):
                    self._set_state(NO_CREDS)
                else:
                    wait_s = self._run_connection(creds, authorize)
            except Exception as e:
                Logger.error(f"[DiscordRPC] manager error: {e}")
                wait_s = 5.0
            self._wake.wait(wait_s)
            self._wake.clear()

    def _run_connection(self, creds, authorize):
        """One full connect attempt. Returns how long to wait before retrying
        (None = wait for an explicit wake)."""
        handle = self._open_pipe()
        if handle is None:
            self._set_state(NO_DISCORD)
            return 5.0

        self._conn_dead.clear()
        self._ready_evt.clear()
        self._needs_auth = False
        self._recv_buf = bytearray()
        self._outgoing.clear()
        self._handle = handle
        threading.Thread(target=self._io_loop, daemon=True, name="discord-io").start()

        try:
            self._set_state(CONNECTING)
            self._enqueue(OP_HANDSHAKE, {"v": 1, "client_id": str(creds["client_id"])})
            if not self._ready_evt.wait(10.0):
                raise TimeoutError("no READY after handshake")

            self._set_state(AUTHENTICATING)
            token = self._ensure_token(creds)
            if not token:
                if not authorize:
                    self._set_state(NEEDS_CONNECT)
                    return None  # wait for the user to click Connect
                self._set_state(AWAITING_APPROVAL)
                data = self.request(
                    "AUTHORIZE",
                    {"client_id": str(creds["client_id"]), "scopes": SCOPES},
                    timeout=120.0,
                )
                token = self._exchange_code(creds, data["code"])
                self._set_state(AUTHENTICATING)

            try:
                auth = self.request("AUTHENTICATE", {"access_token": token})
            except DiscordRPCError:
                # stored token stale? try one refresh, then fall back to Connect
                token = self._refresh_token(creds)
                if not token:
                    self._clear_tokens()
                    self._set_state(NEEDS_CONNECT, "Session expired — click Connect")
                    return None
                auth = self.request("AUTHENTICATE", {"access_token": token})

            user = (auth.get("user") or {})
            with self._lock:
                self._creds["user"] = {"id": user.get("id"), "username": user.get("username")}
                self._authorize_requested = False
            self._persist_creds()

            # subscriptions do not survive reconnects — always re-subscribe
            self.request("SUBSCRIBE", {}, evt="VOICE_SETTINGS_UPDATE")
            self._apply_server_voice(self.request("GET_VOICE_SETTINGS"), force=True)
            self._set_state(READY)
            Logger.info(f"[DiscordRPC] Ready (user: {user.get('username')})")

            self._conn_dead.wait()  # hold until the connection dies
            if self._needs_auth:
                return 0.5  # immediate reconnect + reauth
            return 3.0
        except DiscordRPCError as e:
            Logger.error(f"[DiscordRPC] auth error: {e}")
            self._set_state(AUTH_FAILED, str(e.data.get("message") or e))
            return None
        except requests.RequestException as e:
            Logger.error(f"[DiscordRPC] token exchange failed: {e}")
            self._set_state(AUTH_FAILED, "Token exchange failed (network or bad client secret)")
            return None
        except (TimeoutError, ConnectionError, OSError, pywintypes.error) as e:
            Logger.info(f"[DiscordRPC] connection attempt failed: {e}")
            self._set_state(NO_DISCORD)
            return 5.0
        finally:
            self._kill_pipe()

    # ---------------------------------------------------------------- auth

    def _ensure_token(self, creds):
        token = creds.get("access_token")
        expires_at = creds.get("expires_at") or 0
        if token and time.time() < expires_at - 3600:
            return token
        if creds.get("refresh_token"):
            refreshed = self._refresh_token(creds)
            if refreshed:
                return refreshed
        return token or None

    def _refresh_token(self, creds):
        refresh = creds.get("refresh_token")
        if not refresh:
            return None
        try:
            resp = requests.post(TOKEN_URL, data={
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": str(creds["client_id"]),
                "client_secret": creds["client_secret"],
            }, timeout=10)
            resp.raise_for_status()
            return self._store_token_response(resp.json())
        except requests.RequestException as e:
            Logger.warning(f"[DiscordRPC] token refresh failed: {e}")
            return None

    def _exchange_code(self, creds, code):
        resp = requests.post(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": str(creds["client_id"]),
            "client_secret": creds["client_secret"],
        }, timeout=10)
        resp.raise_for_status()
        return self._store_token_response(resp.json())

    def _store_token_response(self, data):
        with self._lock:
            self._creds["access_token"] = data["access_token"]
            self._creds["refresh_token"] = data.get("refresh_token", self._creds.get("refresh_token"))
            self._creds["expires_at"] = time.time() + data.get("expires_in", 604800)
        self._persist_creds()
        return data["access_token"]

    def _clear_tokens(self):
        with self._lock:
            for k in ("access_token", "refresh_token", "expires_at"):
                self._creds.pop(k, None)
        self._persist_creds()

    def _persist_creds(self):
        """Merge-write into global settings (set_global_settings REPLACES the
        payload, so never write without merging)."""
        try:
            merged = dict(self.plugin.global_settings or {})
            with self._lock:
                merged["discord"] = dict(self._creds)
            self.plugin.set_global_settings(merged)
        except Exception as e:
            Logger.error(f"[DiscordRPC] failed to persist credentials: {e}")

    # ------------------------------------------------------------- display

    def _apply_server_voice(self, data, force=False):
        now = time.monotonic()
        with self._lock:
            def stale(field):
                return force or now - self._local_ts.get(field, 0) > ECHO_SUPPRESS_S
            out = data.get("output") or {}
            inp = data.get("input") or {}
            if "volume" in out and stale("output_volume"):
                self._voice["output_volume"] = float(out["volume"])
            if "volume" in inp and stale("input_volume"):
                self._voice["input_volume"] = float(inp["volume"])
            if "deaf" in data and stale("deaf"):
                self._voice["deaf"] = bool(data["deaf"])
            if "mute" in data and stale("mute"):
                self._voice["mute"] = bool(data["mute"])
        self._notify()

    def _set_state(self, state, detail=""):
        with self._lock:
            if self._state == state and self._detail == detail:
                return
            self._state = state
            self._detail = detail
        Logger.info(f"[DiscordRPC] state -> {state}{f' ({detail})' if detail else ''}")
        self._notify()

    def _set_detail(self, detail):
        with self._lock:
            self._detail = detail
        self._notify()

    def _notify(self):
        with self._lock:
            listeners = list(self._listeners)
        status = self.status()
        for cb in listeners:
            try:
                cb(status)
            except Exception as e:
                Logger.error(f"[DiscordRPC] listener error: {e}")


_instance = None
_instance_lock = threading.Lock()


def get_discord_rpc(plugin) -> DiscordRPC:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = DiscordRPC(plugin)
        return _instance
