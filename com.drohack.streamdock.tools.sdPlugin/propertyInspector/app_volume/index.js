// appvolume.js

// DOM cache
const $dom = {
    appSelect: document.getElementById("selected_app")
};

// Populate dropdown
function populateAppDropdown(appList) {
    if (!$dom.appSelect) return;
    $dom.appSelect.innerHTML = "";
    appList.forEach(app => {
        const opt = document.createElement("option");
        opt.value = app.value;   // just the app name, e.g., Discord.exe
        opt.textContent = app.label; // app name without .exe
        $dom.appSelect.appendChild(opt);
    });
}

// Save selected app and request immediate update
function selectApp(appName) {
    if (!appName) return;
    console.log("Selected app:", appName);
    $websocket.saveData({ selected_app: appName });
    // Force Python to update display immediately
    $websocket.send({ event: "forceVolumeUpdate", app: appName });
}

// --- Property Inspector Event Handlers ---
const $propEvent = {
    didReceiveSettings(data) {
        const settings = data?.payload?.settings || {};
        if (settings.selected_app && $dom.appSelect) {
            $dom.appSelect.value = settings.selected_app;
            selectApp(settings.selected_app);
        }
    },

    sendToPropertyInspector(data) {
        console.log("sendToPropertyInspector", data);
        if (data.event === "updateAppList" && Array.isArray(data.app_list)) {
            populateAppDropdown(data.app_list);
            if (data.selected_app && $dom.appSelect) {
                $dom.appSelect.value = data.selected_app;
                selectApp(data.selected_app);
            }
        }
    },

    didReceiveGlobalSettings(data) {
        console.log("didReceiveGlobalSettings", data);
    }
};

// Attach listeners once DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    if ($dom.appSelect) {
        $dom.appSelect.addEventListener("change", e => {
            const selected = e.target.value;
            selectApp(selected);
        });
    }
});
