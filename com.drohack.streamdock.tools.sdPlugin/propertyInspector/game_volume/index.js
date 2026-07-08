// Game Volume PI: pick which apps the knob must NOT control.

const $dom = {
    excludeList: document.getElementById("exclude_list"),
};

function populate(appList, exclude) {
    if (!$dom.excludeList) return;
    const excludeLower = (exclude || []).map(e => e.toLowerCase());
    $dom.excludeList.innerHTML = "";
    const names = new Map();
    (appList || []).forEach(app => names.set(app.value.toLowerCase(), app));
    // make sure currently-excluded apps appear even if not running
    (exclude || []).forEach(name => {
        if (!names.has(name.toLowerCase())) {
            names.set(name.toLowerCase(), { value: name, label: name.replace(".exe", "") });
        }
    });
    for (const app of names.values()) {
        const opt = document.createElement("option");
        opt.value = app.value;
        opt.textContent = app.label;
        opt.selected = excludeLower.includes(app.value.toLowerCase());
        $dom.excludeList.appendChild(opt);
    }
}

const $propEvent = {
    didReceiveSettings(data) { },

    sendToPropertyInspector(data) {
        if (data.event === "updateGameVolume") {
            populate(data.app_list, data.exclude);
        }
    },

    didReceiveGlobalSettings(data) { },
};

document.addEventListener("DOMContentLoaded", () => {
    $dom.excludeList?.addEventListener("change", () => {
        const exclude = Array.from($dom.excludeList.selectedOptions).map(o => o.value);
        $websocket.sendToPlugin({ event: "setExclude", exclude });
    });
});
