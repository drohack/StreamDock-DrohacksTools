import base64
import io
import time
from PIL import Image, ImageDraw
from src.core.action import Action
from src.core.logger import Logger

from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from comtypes import CoInitialize, CoUninitialize, CLSCTX_ALL


class Volume(Action):
    # Re-activating the endpoint on every call is expensive and can fail
    # transiently under fast dial rotation; cache it briefly instead.
    INTERFACE_TTL = 1.0  # seconds before re-activating (tracks device switches)

    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)

        # Initialize COM once for this instance
        CoInitialize()
        self.volume = None
        self._iface_ts = 0.0
        self.volume = self.get_volume_interface(force=True)

        self.update_volume_display()  # Initial display update
        self.plugin.timer.set_interval(
            f'volume_update_{context}',
            200,
            self.update_volume_display
        )
        Logger.info(f"[VolumeAction] Initialized with context {context}")

    def __del__(self):
        try:
            CoUninitialize()
        except:
            pass

    def generate_volume_image(self, volume_percent, is_muted=False):
        """Generate a 72x72 image with a green bar that grows/shrinks, or red when muted."""
        width, height = 72, 72
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))  # transparent background
        draw = ImageDraw.Draw(img)

        if volume_percent > 0:
            # Calculate fill height (bottom to top)
            fill_height = int((volume_percent / 100) * height)
            fill_y = height - fill_height

            # Choose color
            fill_color = (255, 0, 0, 255) if is_muted else (0, 255, 0, 255)

            # Draw filled rectangle from bottom up
            draw.rectangle([0, fill_y, width, height], fill=fill_color)

        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"

    def get_volume_interface(self, force=False):
        """Return the endpoint interface, re-activating if stale or forced."""
        now = time.monotonic()
        if force or self.volume is None or now - self._iface_ts > self.INTERFACE_TTL:
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.volume = interface.QueryInterface(IAudioEndpointVolume)
            self._iface_ts = now
        return self.volume

    def update_volume_display(self):
        try:
            volume = self.get_volume_interface()  # refresh in case device changed
            current_volume = int(round(volume.GetMasterVolumeLevelScalar() * 100))
            is_muted = volume.GetMute()

            # Text overlay
            if is_muted:
                display = "MUTE"
            elif current_volume == 100:
                display = "MAX"
            elif current_volume < 10:
                display = f"0{current_volume}"
            else:
                display = f"{current_volume}"

            # Update only if changed
            current_state = (current_volume, is_muted)
            if current_state != getattr(self, "_last_state", None):
                self._last_state = current_state
                self.set_title(display)

                # Generate and set background image
                bg_image = self.generate_volume_image(current_volume, is_muted)
                self.set_image(bg_image)

        except Exception as e:
            self._iface_ts = 0.0  # force re-activation on next call
            Logger.error(f"[VolumeAction] Exception in update_volume_display: {e}")

    def mute_toggle(self):
        try:
            volume = self.get_volume_interface()
            current_mute = volume.GetMute()
            volume.SetMute(0 if current_mute else 1, None)
            self.update_volume_display()
        except Exception as e:
            self._iface_ts = 0.0
            Logger.error(f"[VolumeAction] Exception in mute_toggle: {e}")

    def change_volume_percent(self, delta_percent: int):
        """Change volume by delta_percent (integer percent).

        Retries once with a fresh endpoint interface so a transient COM
        failure doesn't swallow the dial tick.
        """
        for attempt in range(2):
            try:
                volume = self.get_volume_interface(force=attempt > 0)
                # Read current percent (rounded)
                current_p = int(round(volume.GetMasterVolumeLevelScalar() * 100))

                # Compute new percent and clamp
                new_p = max(0, min(100, current_p + delta_percent))

                # Set exact scalar
                volume.SetMasterVolumeLevelScalar(new_p / 100.0, None)
                self.update_volume_display()
                return
            except Exception as e:
                if attempt == 0:
                    Logger.warning(f"[VolumeAction] change_volume_percent retrying after: {e}")
                else:
                    Logger.error(f"[VolumeAction] Exception in change_volume_percent: {e}")

    # Events
    def on_key_down(self, payload: dict):
        Logger.info(f"[VolumeAction] Key down event with payload: {payload}")
        self.mute_toggle()

    def on_dial_down(self, payload: dict):
        Logger.info(f"[VolumeAction] Dial down event with payload: {payload}")
        self.mute_toggle()

    def on_dial_rotate(self, payload: dict):
        ticks = payload.get("ticks", 0)
        step_percent = 5  # change this to taste
        if ticks != 0:
            self.change_volume_percent(ticks * step_percent)

    def on_will_disappear(self):
        # Clear the timer when action disappears
        self.plugin.timer.clear_interval(f'volume_update_{self.context}')
        Logger.info(f"[VolumeAction] Will disappear for context {self.context}")

    # Extra events to skip
    def on_did_receive_global_settings(self, settings: dict):
        # don't log the payload — global settings hold Discord OAuth secrets
        Logger.info(f"[VolumeAction] Received global settings ({len(settings or {})} keys)")

    def on_key_up(self, payload: dict):
        self.set_state(1)
        Logger.info(f"[VolumeAction] Key up event with payload: {payload}")

    def on_dial_up(self, payload: dict):
        Logger.info(f"[VolumeAction] Dial up event with payload: {payload}")

    def on_device_did_connect(self, payload: dict):
        Logger.info(f"[VolumeAction] Device connected with payload: {payload}")

    def on_device_did_disconnect(self, data: dict):
        Logger.info(f"[VolumeAction] Device disconnected with data: {data}")

    def on_application_did_launch(self, data: dict):
        Logger.info(f"[VolumeAction] Application launched with data: {data}")

    def on_application_did_terminate(self, data: dict):
        Logger.info(f"[VolumeAction] Application terminated with data: {data}")

    def on_system_did_wake_up(self, data: dict):
        Logger.info(f"[VolumeAction] System woke up with data: {data}")

    def on_property_inspector_did_appear(self, data: dict):
        Logger.info(f"[VolumeAction] Property inspector appeared with data: {data}")

    def on_property_inspector_did_disappear(self, data: dict):
        Logger.info(f"[VolumeAction] Property inspector disappeared with data: {data}")

    def on_send_to_plugin(self, payload: dict):
        Logger.info(f"[VolumeAction] Received message from property inspector with payload: {payload}")