// Shared property inspector logic for the Discord actions (voice knob + mute
// button). Handles credential entry, the Connect flow, and status display.

const $discordDom = {
    clientId: document.getElementById("client_id"),
    clientSecret: document.getElementById("client_secret"),
    connectBtn: document.getElementById("connect_btn"),
    forgetBtn: document.getElementById("forget_btn"),
    status: document.getElementById("discord_status"),
};

const STATUS_TEXT = {
    no_creds: "Setup required: paste your Discord app credentials and Save",
    needs_connect: "Credentials saved — click Connect to authorize",
    no_discord: "Discord is not running",
    connecting: "Connecting to Discord…",
    awaiting_approval: "Waiting for approval — check the popup in Discord",
    authenticating: "Authenticating…",
    ready: "Connected",
    auth_failed: "Authorization failed",
};

function renderDiscordStatus(data) {
    if (!$discordDom.status) return;
    let text = STATUS_TEXT[data.state] || data.state;
    if (data.state === "ready" && data.user && data.user.username) {
        text = `Connected as ${data.user.username}`;
    }
    if (data.detail) {
        text += ` — ${data.detail}`;
    }
    $discordDom.status.textContent = text;
    $discordDom.status.style.color = data.state === "ready" ? "#43b581"
        : (data.state === "auth_failed" ? "#ed4245" : "#cccccc");
}

function saveDiscordCredentials() {
    const client_id = ($discordDom.clientId?.value || "").trim();
    const client_secret = ($discordDom.clientSecret?.value || "").trim();
    if (!client_id || !client_secret) return;
    $websocket.sendToPlugin({ event: "discordSaveCredentials", client_id, client_secret });
}

const $propEvent = {
    didReceiveSettings(data) { },

    sendToPropertyInspector(data) {
        if (data.event === "discordStatus") {
            renderDiscordStatus(data);
            // don't clobber fields while the user is typing; just show whether creds exist
            if (data.has_creds && $discordDom.clientId && !$discordDom.clientId.value) {
                $discordDom.clientId.placeholder = "(saved)";
                if ($discordDom.clientSecret) $discordDom.clientSecret.placeholder = "(saved)";
            }
        }
    },

    didReceiveGlobalSettings(data) { },
};

document.addEventListener("DOMContentLoaded", () => {
    $discordDom.connectBtn?.addEventListener("click", () => {
        saveDiscordCredentials();
        $websocket.sendToPlugin({ event: "discordConnect" });
    });
    $discordDom.forgetBtn?.addEventListener("click", () => {
        $websocket.sendToPlugin({ event: "discordForget" });
    });
    // initial status fetch (plugin also pushes on PI appear)
    setTimeout(() => $websocket.sendToPlugin({ event: "discordGetStatus" }), 300);
});
