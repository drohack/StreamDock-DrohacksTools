// index.js

// DOM cache
const $dom = {
    gifModeRadios: document.querySelectorAll('input[name="gif_mode"]'),
    gifSelectContainer: document.getElementById('gif-select-container'),
    gifSelect: document.getElementById('selected_gif')
};

// --- Property Inspector Event Handlers ---
const $propEvent = {
    didReceiveSettings(data) {
        console.log("didReceiveSettings", data);
        const settings = data?.payload?.settings || {};

        // Restore mode
        if (settings.gif_mode) {
            const radio = document.querySelector(`input[name="gif_mode"][value="${settings.gif_mode}"]`);
            if (radio) {
                radio.checked = true;
                toggleGifSelect(settings.gif_mode);
            }
        }

        // Restore selected static GIF
        if (settings.selected_gif && $dom.gifSelect) {
            $dom.gifSelect.value = settings.selected_gif;
        }
    },

    sendToPropertyInspector(data) {
		console.log("sendToPropertyInspector", data);

		if (data.event === "updateGifList" && Array.isArray(data.gif_files)) {
			populateGifDropdown(data.gif_files);

			// Restore gif_mode and selected_gif if provided
			if (data.gif_mode) {
				const radio = document.querySelector(`input[name="gif_mode"][value="${data.gif_mode}"]`);
				if (radio) {
					radio.checked = true;
					toggleGifSelect(data.gif_mode);
				}
			}
			if (data.selected_gif && $dom.gifSelect) {
				$dom.gifSelect.value = data.selected_gif;
			}
		}
	},

    didReceiveGlobalSettings(data) {
        console.log("didReceiveGlobalSettings", data);
    }
};

// --- UI Logic ---
function toggleGifSelect(mode) {
    $dom.gifSelectContainer.style.display = (mode === "static") ? "flex" : "none";
}

function populateGifDropdown(gifFiles) {
    if (!$dom.gifSelect) return;
    $dom.gifSelect.innerHTML = "";
    gifFiles.forEach(gif => {
        const opt = document.createElement("option");
        opt.value = gif.value;
        opt.textContent = gif.label;
        $dom.gifSelect.appendChild(opt);
    });
}

// Attach listeners once DOM ready
document.addEventListener("DOMContentLoaded", () => {
    // Mode radio buttons
    $dom.gifModeRadios.forEach(radio => {
        radio.addEventListener('change', e => {
            const mode = e.target.value;
            console.log("Saving gif_mode", mode);
            toggleGifSelect(mode);

            if (mode === "static" && $dom.gifSelect) {
                const selected = $dom.gifSelect.value;
                console.log("Saving gif_mode + selected_gif", mode, selected);
                $websocket.saveData({ gif_mode: mode, selected_gif: selected });
            } else {
                $websocket.saveData({ gif_mode: mode });
            }
        });
    });

    // Dropdown for static GIFs
    if ($dom.gifSelect) {
        $dom.gifSelect.addEventListener('change', e => {
            const selected = e.target.value;
            console.log("Saving selected_gif", selected);
            $websocket.saveData({ gif_mode: "static", selected_gif: selected });
        });
    }
});
