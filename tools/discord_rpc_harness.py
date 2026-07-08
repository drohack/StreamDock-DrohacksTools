"""Manual live test for src/core/discord_rpc.py.

Usage (from repo root, with the venv active):
    python tools/discord_rpc_harness.py <CLIENT_ID> <CLIENT_SECRET>

Uses YOUR OWN Discord application credentials (create one at
https://discord.com/developers/applications, add redirect URL
http://localhost). On first run Discord shows a consent popup — approve it.
The script authorizes, authenticates, prints the live voice settings, then
listens for changes: move the Output Volume slider or toggle mute/deafen in
Discord and watch the events print. Ctrl+C to quit.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.discord_rpc import get_discord_rpc, READY, NEEDS_CONNECT


class FakePlugin:
    """Stands in for the StreamDock Plugin object; persists creds in memory."""
    global_settings = {}

    def set_global_settings(self, payload):
        self.global_settings = payload

    def get_global_settings(self):
        pass


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    client_id, client_secret = sys.argv[1], sys.argv[2]

    rpc = get_discord_rpc(FakePlugin())
    rpc.acquire(lambda s: print(
        f"[status] {s['state']}  voice={s['voice']}"
        + (f"  detail={s['detail']}" if s['detail'] else ""), flush=True))
    rpc.save_credentials(client_id, client_secret)
    rpc.begin_authorize()

    print("Waiting for connection (approve the Discord popup if it appears)...", flush=True)
    deadline = time.time() + 130
    while time.time() < deadline and rpc.state != READY:
        time.sleep(0.5)

    if rpc.state != READY:
        print(f"FAILED to reach READY (state={rpc.state})", flush=True)
        sys.exit(1)

    print(f"READY. voice={rpc.voice_snapshot()}", flush=True)
    print("Listening 30s — change volume/mute/deafen in Discord to see events...", flush=True)
    try:
        time.sleep(30)
    except KeyboardInterrupt:
        pass
    print(f"Done: final voice={rpc.voice_snapshot()}", flush=True)


if __name__ == "__main__":
    main()
