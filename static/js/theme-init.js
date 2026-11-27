(() => {
    const root = document.documentElement;
    const themes = ["ivory", "lavender", "mauve", "rose", "sage", "plum"];
    const savedTheme = window.localStorage.getItem(`webthon-theme:${root.dataset.themeKey}`);
    if (themes.includes(savedTheme)) {
        root.dataset.theme = savedTheme;
    }
})();
