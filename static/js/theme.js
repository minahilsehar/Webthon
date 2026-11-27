document.addEventListener("alpine:init", () => {
    const root = document.documentElement;
    const themeColorMeta = document.querySelector('meta[name="theme-color"]');
    const themes = ["ivory", "lavender", "mauve", "rose", "sage", "plum"];
    const key = `webthon-theme:${root.dataset.themeKey}`;
    const lastLightKey = `${key}:last-light`;
    const savedLastLight = window.localStorage.getItem(lastLightKey);
    const updateBrowserThemeColor = () => {
        if (themeColorMeta) {
            themeColorMeta.content = window.getComputedStyle(root).getPropertyValue("--bg").trim();
        }
    };

    Alpine.store("theme", {
        current: root.dataset.theme,
        lastLight: themes.includes(savedLastLight) && savedLastLight !== "plum" ? savedLastLight : "ivory",
        status: "",
        select(theme) {
            if (!themes.includes(theme)) {
                return;
            }

            this.current = theme;
            root.dataset.theme = theme;
            updateBrowserThemeColor();
            window.localStorage.setItem(key, theme);
            if (theme !== "plum") {
                this.lastLight = theme;
                window.localStorage.setItem(lastLightKey, theme);
            }
            this.status = "Theme changed on this device.";
        },
        toggle() {
            this.select(this.current === "plum" ? this.lastLight : "plum");
            const form = document.querySelector(".theme-picker[hx-post]");
            if (form) {
                const input = form.querySelector(`input[value="${this.current}"]`);
                if (input) {
                    input.checked = true;
                    input.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
        },
    });
    updateBrowserThemeColor();
});
