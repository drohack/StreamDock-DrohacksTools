"""Discord mic mute button.

Press: toggle mic mute. If currently deafened, one press clears BOTH deafen
and mute (matching how you'd want to rejoin a conversation).
Face: mic state icon (live / muted / deafened) with the current voice output
volume as the title, so you can see at a glance whether chat is maxed out.
"""

from src.core.action import Action
from src.core.logger import Logger
from src.core.discord_rpc import get_discord_rpc, READY
from src.core import discord_faces


class DiscordMute(Action):
    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)
        self._pi_visible = False
        self._last_face = None
        self.rpc = get_discord_rpc(plugin)
        self.rpc.acquire(self._on_rpc_status)
        self._render(self.rpc.status())
        Logger.info(f"[DiscordMute] Initialized with context {context}")

    # ------------------------------------------------------------- display

    def _on_rpc_status(self, status: dict):
        self._render(status)
        if self._pi_visible:
            self._push_status(status)

    def _render(self, status: dict):
        state = status["state"]
        voice = status["voice"]
        if state == READY:
            face = ("ready", voice["mute"], voice["deaf"], int(round(voice["output_volume"])))
        else:
            face = (state,)
        if face == self._last_face:
            return
        self._last_face = face
        if state == READY:
            kind = "deafened" if voice["deaf"] else ("muted" if voice["mute"] else "mic")
            # icon + number are composited into the image; clear the title overlay
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

    def on_key_down(self, payload: dict):
        if self.rpc.state != READY:
            self.show_alert()
            return
        snap = self.rpc.voice_snapshot()
        if snap["deaf"]:
            # deafened implies muted; a single press brings you fully back
            self.rpc.set_local_voice({"deaf": False, "mute": False})
            self.rpc.queue_voice_patch({"deaf": False, "mute": False})
        else:
            mute = not snap["mute"]
            self.rpc.set_local_voice({"mute": mute})
            self.rpc.queue_voice_patch({"mute": mute})

    def on_dial_down(self, payload: dict):
        self.on_key_down(payload)

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
        Logger.info(f"[DiscordMute] Will disappear for context {self.context}")
