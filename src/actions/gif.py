import os
import random
import base64
import io
import json
import sys
from PIL import Image, ImageSequence
from src.core.action import Action
from src.core.logger import Logger

class Gif(Action):
    def get_static_path(self, subdir=""):
        """Return absolute path to /static/ (works in PyInstaller and dev)."""
        if getattr(sys, 'frozen', False):  
            # Running from a PyInstaller bundle
            base_path = sys._MEIPASS  # temp unpack dir
            # But your plugin folder layout has /plugin/static outside the exe,
            # so instead anchor to the exe’s real folder:
            base_path = os.path.dirname(sys.executable)
        else:
            # Normal dev run
            base_path = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(base_path, "static", subdir)

    def __init__(self, action: str, context: str, settings: dict, plugin):
        super().__init__(action, context, settings, plugin)
        self.context = context
        self.plugin = plugin

        # GIF Mode to determine how to pick next gif: random, shuffle, order, static
        #   random: pure random each time
        #   shuffle: random but no repeats until all shown
        #   order: go through in order
        #   static: always show the selected gif
        self.gif_mode = settings.get('gif_mode', 'random')  
        self.gif_queue = []  # For shuffle mode  
        self.current_gif_index = 0  # For order mode
        self.selected_gif = settings.get('selected_gif') # For static mode
        self.old_selected_gif = settings.get('selected_gif') # To track changes in static mode


        self.gif_folder = self.get_static_path("gifs")
        self.current_frames = []
        self.current_index = 0
        self.frame_delay = 100  # ms per frame (default, will try to read from gif metadata)
        self.switch_interval = 30000  # ms before switching to a new gif

        if self.gif_mode == "static":
            if self.selected_gif:
                self.load_static_gif(self.selected_gif)
            else:
                self.logger.warning("Static mode selected but no selected_gif found in settings.")
                # maybe fall back to first available gif or just skip
                return
        else:
            # Pick first gif
            self.load_next_gif()

            # Timer to step through frames
            self.plugin.timer.set_interval(
                f'gif_frame_{context}',
                self.frame_delay,
                self.next_frame
            )

            # Timer to switch gifs
            self.plugin.timer.set_interval(
                f'gif_switch_{context}',
                self.switch_interval,
                self.load_next_gif
            )

        Logger.info(f"[GifAction] Initialized with context {context}")

    def load_next_gif(self):
        try:
            files = [f for f in os.listdir(self.gif_folder) if f.lower().endswith(".gif")]
            if not files:
                Logger.error(f"[GifAction] No GIFs found in {self.gif_folder}")
                return

            if self.gif_mode == 'random':  
                gif_file = os.path.join(self.gif_folder, random.choice(files))  
            elif self.gif_mode == 'order':  
                gif_file = os.path.join(self.gif_folder, files[self.current_gif_index % len(files)])  
                self.current_gif_index += 1  
            elif self.gif_mode == 'shuffle':  
                if not self.gif_queue:  
                    self.gif_queue = files.copy()  
                    random.shuffle(self.gif_queue)  
                gif_file = os.path.join(self.gif_folder, self.gif_queue.pop(0)) 
            
            #Logger.info(f"[GifAction] Loading GIF: {gif_file}")
            self.current_frames.clear()
            self.current_index = 0

            with Image.open(gif_file) as im:
                # Get frame delay if available
                if "duration" in im.info:
                    self.frame_delay = im.info["duration"]
                else:
                    self.frame_delay = 100  # fallback

                for frame in ImageSequence.Iterator(im):
                    # Convert to RGBA and resize
                    frame = frame.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)

                    # Save to buffer
                    buf = io.BytesIO()
                    frame.save(buf, format="PNG")
                    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
                    self.current_frames.append(f"data:image/png;base64,{b64_str}")


            # Reset timer with new frame delay
            self.plugin.timer.clear_interval(f'gif_frame_{self.context}')
            self.plugin.timer.set_interval(
                f'gif_frame_{self.context}',
                self.frame_delay,
                self.next_frame
            )

        except Exception as e:
            Logger.error(f"[GifAction] Failed to load gif: {e}")
    
    def load_static_gif(self, filename: str):  
        """Load a specific GIF file"""  
        try:  
            gif_file = os.path.join(self.gif_folder, filename)  
            if not os.path.exists(gif_file):  
                Logger.error(f"[GifAction] Static GIF not found: {gif_file}")  
                return  
                
            # Clear existing timers for static mode  
            self.plugin.timer.clear_interval(f'gif_switch_{self.context}')  
            
            # Load the specific GIF (reuse existing loading logic)  
            self.current_frames.clear()  
            self.current_index = 0  
            
            with Image.open(gif_file) as im:  
                if "duration" in im.info:  
                    self.frame_delay = im.info["duration"]  
                else:  
                    self.frame_delay = 100  
                    
                for frame in ImageSequence.Iterator(im):  
                    frame = frame.convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)  
                    buf = io.BytesIO()  
                    frame.save(buf, format="PNG")  
                    b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")  
                    self.current_frames.append(f"data:image/png;base64,{b64_str}")  
            
            # Reset frame timer  
            self.plugin.timer.clear_interval(f'gif_frame_{self.context}')  
            self.plugin.timer.set_interval(  
                f'gif_frame_{self.context}',  
                self.frame_delay,  
                self.next_frame  
            )  
            
        except Exception as e:  
            Logger.error(f"[GifAction] Failed to load static gif: {e}")

    def next_frame(self):
        try:
            if not self.current_frames:
                return

            frame_b64 = self.current_frames[self.current_index]
            self.set_image(frame_b64)  # SDK call to update the device screen

            self.current_index = (self.current_index + 1) % len(self.current_frames)

        except Exception as e:
            Logger.error(f"[GifAction] Exception in next_frame: {e}")

    # Events
    def on_key_down(self, payload: dict):
        Logger.info(f"[GifAction] Key down event with payload: {payload}")

        # Load a new random gif immediately
        self.load_next_gif()

        # Reset the switch timer so it restarts counting from now
        self.plugin.timer.clear_interval(f'gif_switch_{self.context}')
        self.plugin.timer.set_interval(
            f'gif_switch_{self.context}',
            self.switch_interval,
            self.load_next_gif
        )
    
    def on_did_receive_settings(self, payload: dict):
        Logger.info(f"[GifAction] Did recieve Setting with payload: {payload}")
        try:
            old_mode = self.gif_mode  
            self.gif_mode = payload.get('gif_mode', old_mode if old_mode is not None else 'random')
            
            # If mode changed, reset state and load new gif
            if self.gif_mode == 'static':
                self.selected_gif = payload.get('selected_gif', None)
                if old_mode != self.gif_mode or self.selected_gif != self.old_selected_gif:
                    # Stop the gif switching timer
                    self.plugin.timer.clear_interval(f'gif_switch_{self.context}')
                    self.old_selected_gif = self.selected_gif
                    self.load_static_gif(self.selected_gif)
            elif old_mode != self.gif_mode:  
                if self.gif_mode == 'order':  
                    self.current_gif_index = 0  
                elif self.gif_mode == 'shuffle':  
                    self.gif_queue = []  
                
                # Load a new random gif immediately
                self.load_next_gif()
                # Reset the switch timer so it restarts counting from now
                self.plugin.timer.clear_interval(f'gif_switch_{self.context}')
                self.plugin.timer.set_interval(
                    f'gif_switch_{self.context}',
                    self.switch_interval,
                    self.load_next_gif
                )
        except Exception as e:
            Logger.error(f"[GifAction] Exception in on_did_receive_settings: {e}")
    
    def on_property_inspector_did_appear(self, payload: dict):
        Logger.info(f"[GifAction] Property inspector appeared with payload: {payload}")
        try:  
            files = [f for f in os.listdir(self.gif_folder) if f.lower().endswith(".gif")]  
            gif_options = [{"value": f, "label": os.path.splitext(f)[0]} for f in files]  
            
            self.send_to_property_inspector({
                "event": "updateGifList",
                "gif_files": gif_options,
                "gif_mode": self.gif_mode,
                "selected_gif": self.selected_gif
            })
        except Exception as e:  
            Logger.error(f"[GifAction] Failed to send GIF list: {e}")  

    def on_dial_down(self, payload: dict):
        Logger.info(f"[GifAction] Dial down event with payload: {payload}")

    def on_dial_rotate(self, payload: dict):
        Logger.info(f"[GifAction] Dial rotate event with payload: {payload}")

    def on_will_disappear(self):
        # Clear the timer when action disappears
        self.plugin.timer.clear_interval(f'time_update_{self.context}')
        Logger.info(f"[TimeAction] Will disappear for context {self.context}")

    # Extra events to skip
    def on_did_receive_global_settings(self, settings: dict):
        Logger.info(f"[GifAction] Received global settings: {settings}")

    def on_key_up(self, payload: dict):
        self.set_state(1)
        Logger.info(f"[GifAction] Key up event with payload: {payload}")

    def on_dial_up(self, payload: dict):
        Logger.info(f"[GifAction] Dial up event with payload: {payload}")

    def on_device_did_connect(self, payload: dict):
        Logger.info(f"[GifAction] Device connected with payload: {payload}")

    def on_device_did_disconnect(self, data: dict):
        Logger.info(f"[GifAction] Device disconnected with data: {data}")

    def on_application_did_launch(self, data: dict):
        Logger.info(f"[GifAction] Application launched with data: {data}")

    def on_application_did_terminate(self, data: dict):
        Logger.info(f"[GifAction] Application terminated with data: {data}")

    def on_system_did_wake_up(self, data: dict):
        Logger.info(f"[GifAction] System woke up with data: {data}")

    def on_property_inspector_did_disappear(self, data: dict):
        Logger.info(f"[GifAction] Property inspector disappeared with data: {data}")

    def on_send_to_plugin(self, payload: dict):
        Logger.info(f"[GifAction] Received message from property inspector with payload: {payload}")