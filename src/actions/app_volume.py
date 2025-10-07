import base64
import io
import os
import ctypes
import psutil
from PIL import Image, ImageDraw, ImageFont
from src.core.action import Action
from src.core.logger import Logger
from pycaw.pycaw import AudioUtilities
from comtypes import CoInitialize, CoUninitialize

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
shell32 = ctypes.windll.shell32

class AppVolume(Action):
    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)
        CoInitialize()

        self.selected_app = settings.get("selected_app", None)
        self.volume_interfaces = []  # all matching sessions
        self._last_state = None
        self.current_volume = None
        self.current_muted = None

        self.list_audio_sessions() # initalize app list

        self.plugin.timer.set_interval(
            f'app_volume_update_{context}', 300, self.update_volume_display
        )

        Logger.info(f"[AppVolume] Initialized with context {context}, selected app: {self.selected_app}")

    def __del__(self):
        try:
            CoUninitialize()
        except:
            pass

    # --- Get all active sessions for selected app ---
    def update_volume_interfaces(self):
        self.volume_interfaces = []
        if not self.selected_app:
            return
        app_name = os.path.basename(self.selected_app)
        for s in AudioUtilities.GetAllSessions():
            try:
                if s.Process and os.path.basename(s.Process.name()) == app_name:
                    self.volume_interfaces.append(s.SimpleAudioVolume)
            except Exception as e:
                Logger.warning(f"[AppVolume] update_volume_interfaces - Error accessing session process: {e}")
                continue

    # --- List apps for dropdown (no IDs) ---
    @staticmethod
    def list_audio_sessions():
        sessions = AudioUtilities.GetAllSessions()
        apps = []
        seen = set()
        for s in sessions:
            try:
                if s.Process:
                    name = os.path.basename(s.Process.name())
                    if name not in seen:
                        apps.append({"value": name, "label": name.replace(".exe", "")})
                        seen.add(name)
            except Exception as e:
                Logger.warning(f"[AppVolume] list_audio_sessions - Error accessing session process: {e}")
                continue
        return apps

    # --- Convert HICON to PIL Image ---
    @staticmethod
    def hicon_to_image(hicon, size=(36, 36)):
        hdc = user32.GetDC(0)
        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, size[0], size[1])
        gdi32.SelectObject(memdc, bmp)

        if not user32.DrawIconEx(memdc, 0, 0, hicon, size[0], size[1], 0, 0, 3):
            Logger.error("DrawIconEx failed")
            return None

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", ctypes.c_uint32 * 3),
            ]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = size[0]
        bmi.bmiHeader.biHeight = -size[1]  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        buf = (ctypes.c_ubyte * (size[0] * size[1] * 4))()
        gdi32.GetDIBits(memdc, bmp, 0, size[1], buf, ctypes.byref(bmi), 0)

        img = Image.frombuffer("RGBA", size, bytes(buf), "raw", "BGRA", 0, 1)

        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)
        user32.DestroyIcon(hicon)

        return img

    # --- Extract 36x36 icon from exe ---
    @staticmethod
    def get_app_icon(exe_path):
        try:
            # create HICON pointers
            large = ctypes.c_void_p()
            small = ctypes.c_void_p()
            # extract first icon
            n = shell32.ExtractIconExW(exe_path, 0, ctypes.byref(large), ctypes.byref(small), 1)
            hicon = large.value or small.value
            if not hicon:
                return None
            return AppVolume.hicon_to_image(hicon, (36, 36))
        except Exception as e:
            Logger.error(f"[AppVolume] Error extracting icon: {e}")
            return None
    
    def find_process_exe(self, process_name: str):
        """Return the full exe path for a running process matching process_name."""
        process_name = process_name.lower()
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                if proc.info["name"] and process_name in proc.info["name"].lower():
                    return proc.info["exe"]
            except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
                Logger.warning(f"[AppVolume] Could not access process {proc.pid}: {e}")
                continue
        return None

    # --- Generate volume image with full background and icon + text ---
    def generate_volume_image(self, volume_percent, is_muted=False):
        width, height = 72, 72
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))  # transparent

        # Full-background volume fill
        fill_height = int((volume_percent / 100) * height)
        fill_color = (0, 255, 0, 255) if not is_muted else (255, 0, 0, 255)
        fill_img = Image.new("RGBA", (width, fill_height), fill_color)
        img.paste(fill_img, (0, height - fill_height))

        # Overlay icon
        icon_size = 36
        icon_bottom_y = (height - icon_size) // 2 + icon_size
        if self.selected_app:
            try:
                exe_path = self.find_process_exe(self.selected_app)
                if exe_path:
                    icon_img = self.get_app_icon(exe_path)
                    if icon_img:
                        icon_x = (width - icon_size) // 2
                        icon_y = (height - icon_size) // 2
                        img.paste(icon_img, (icon_x, icon_y), icon_img)
            except Exception as e:
                Logger.warning(f"[AppVolume] Failed to overlay icon for {self.selected_app}: {e}")

        # Draw volume text below icon (36x18 space)
        text = f"{volume_percent if not is_muted else 'MUTE'}"
        draw = ImageDraw.Draw(img)

        font_size = 16  # fits in 36x18 space
        try:
            font = ImageFont.truetype("arialbd.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        # Measure text using textbbox
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = (width - text_width) // 2
        icon_bottom_y = (height - 36) // 2 + 36
        text_y = icon_bottom_y + ((height - icon_bottom_y - text_height) // 2)

        # Draw text with a black outline (stroke)
        draw.text(
            (text_x, text_y),
            text,
            font=font,
            fill=(255, 255, 255, 255) # white text
        )

        # Convert to base64 for StreamDock
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"


    # --- Update display ---
    def update_volume_display(self):
        try:
            self.update_volume_interfaces()
            if not self.volume_interfaces:
                # Keep title for "No App"
                self.set_title("No App")
                self.set_image(self.generate_volume_image(0, True))
                return

            vols = [v.GetMasterVolume() for v in self.volume_interfaces]
            mutes = [v.GetMute() for v in self.volume_interfaces]
            avg_vol = int(round(sum(vols) / len(vols) * 100))
            is_muted = all(mutes)

            current_state = (avg_vol, is_muted)
            if current_state != self._last_state:
                self._last_state = current_state
                self.current_volume = avg_vol
                self.current_muted = is_muted
                # Remove set_title, text drawn in image now
                self.set_image(self.generate_volume_image(avg_vol, is_muted))
        except Exception as e:
            Logger.error(f"[AppVolume] update_volume_display error: {e}")

    # --- Volume controls ---
    def change_volume_percent(self, delta_percent):
        try:
            for v in self.volume_interfaces:
                current = v.GetMasterVolume()
                new_val = max(0.0, min(1.0, current + delta_percent / 100.0))
                v.SetMasterVolume(new_val, None)
            self.update_volume_display()
        except Exception as e:
            Logger.error(f"[AppVolume] change_volume_percent error: {e}")

    def mute_toggle(self):
        try:
            if not self.volume_interfaces:
                return
            any_muted = all(v.GetMute() for v in self.volume_interfaces)
            for v in self.volume_interfaces:
                v.SetMute(0 if any_muted else 1, None)
            self.update_volume_display()
        except Exception as e:
            Logger.error(f"[AppVolume] mute_toggle error: {e}")

    # --- Event hooks ---
    def on_property_inspector_did_appear(self, payload: dict):
        Logger.info(f"[AppVolume] Property inspector appeared, sending session list")
        try:
            app_list = self.list_audio_sessions()
            self.send_to_property_inspector({
                "event": "updateAppList",
                "app_list": app_list,
                "selected_app": self.selected_app
            })
        except Exception as e:
            Logger.error(f"[AppVolume] Failed to send app list: {e}")

    def on_did_receive_settings(self, payload: dict):
        Logger.info(f"[AppVolume] Received settings: {payload}")
        try:
            new_app = payload.get("selected_app")
            if new_app and new_app != self.selected_app:
                self.selected_app = new_app
                self.update_volume_display()
        except Exception as e:
            Logger.error(f"[AppVolume] Exception in on_did_receive_settings: {e}")

    def on_dial_rotate(self, payload: dict):
        ticks = payload.get("ticks", 0)
        if ticks:
            self.change_volume_percent(ticks * 5)

    def on_dial_down(self, payload: dict):
        self.mute_toggle()

    def on_key_down(self, payload: dict):
        self.mute_toggle()

    def on_will_disappear(self):
        self.plugin.timer.clear_interval(f'app_volume_update_{self.context}')
        Logger.info(f"[AppVolume] Will disappear for context {self.context}")
