"""Discord voice output volume knob.

Rotate: change Discord's Voice & Video "Output Volume" (incoming call voices
only — not pings/soundboard) via the local RPC API. Works whenever Discord is
running; no Windows audio session required.
Press (dial or key): toggle deafen.
"""

from src.core.action import Action
from src.core.logger import Logger
from src.core.discord_rpc import get_discord_rpc, READY
from src.core import discord_faces


class DiscordVoice(Action):
    STEP = 5.0
    MAX_VOLUME = 200.0

    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)
        self._pi_visible = False
        self._last_face = None
        self.rpc = get_discord_rpc(plugin)
        self.rpc.acquire(self._on_rpc_status)
        self._render(self.rpc.status())
        Logger.info(f"[DiscordVoice] Initialized with context {context}")

    # ------------------------------------------------------------- display

    def _on_rpc_status(self, status: dict):
        self._render(status)
        if self._pi_visible:
            self._push_status(status)

    def _render(self, status: dict):
        state = status["state"]
        voice = status["voice"]
        if state == READY:
            face = ("ready", int(round(voice["output_volume"])), voice["deaf"], voice["mute"])
        else:
            face = (state,)
        if face == self._last_face:
            return
        self._last_face = face
        if state == READY:
            # same Discord iconography as the mute button: blue mic gauge that
            # fills with volume, red slashed mic/headphones when muted/deafened
            kind = "deafened" if voice["deaf"] else ("muted" if voice["mute"] else "mic")
            self.set_title("")
            self.set_image(discord_faces.icon_face(kind, voice["output_volume"]))
        else:
            self.set_title(discord_faces.STATE_LABELS.get(state, state))
            self.set_image(discord_faces.state_face())

    def _push_status(self, status: dict):
        self.send_to_property_inspector({
            "event": "discordStatus",
            "state": status["state"],
            "detail": status["detail"],
            "user": status["user"],
            "has_creds": status["has_creds"],
        })

    # -------------------------------------------------------------- events

    def on_dial_rotate(self, payload: dict):
        ticks = payload.get("ticks", 0)
        if not ticks or self.rpc.state != READY:
            return
        current = self.rpc.voice_snapshot()["output_volume"]
        target = max(0.0, min(self.MAX_VOLUME, current + ticks * self.STEP))
        # optimistic: face updates instantly, sender coalesces the IPC writes
        self.rpc.set_local_voice({"output_volume": target})
        self.rpc.queue_voice_patch({"output": {"volume": float(target)}})

    def _toggle_deafen(self):
        if self.rpc.state != READY:
            self.show_alert()
            return
        deaf = not self.rpc.voice_snapshot()["deaf"]
        self.rpc.set_local_voice({"deaf": deaf})
        self.rpc.queue_voice_patch({"deaf": deaf})

    def on_dial_down(self, payload: dict):
        self._toggle_deafen()

    def on_key_down(self, payload: dict):
        self._toggle_deafen()

    # ------------------------------------------------- PI / settings plumbing

    def on_send_to_plugin(self, payload: dict):
        event = payload.get("event")
        if event == "discordSaveCredentials":
            self.rpc.save_credentials(payload.get("client_id", ""), payload.get("client_secret", ""))
        elif event == "discordConnect":
            self.rpc.begin_authorize()
        elif event == "discordForget":
            self.rpc.forget()
        elif event == "discordGetStatus":
            self._push_status(self.rpc.status())

    def on_property_inspector_did_appear(self, data: dict):
        self._pi_visible = True
        self._push_status(self.rpc.status())

    def on_property_inspector_did_disappear(self, data: dict):
        self._pi_visible = False

    def on_did_receive_global_settings(self, settings):
        self.rpc.update_credentials((settings or {}).get("discord") or {})

    def on_will_disappear(self):
        self.rpc.release(self._on_rpc_status)
        Logger.info(f"[DiscordVoice] Will disappear for context {self.context}")
