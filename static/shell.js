(() => {
  const shell = document.querySelector(".shell");
  const sidebar = document.getElementById("primary-sidebar");
  const toggle = document.querySelector(".sidebar-toggle");
  const scrim = document.querySelector(".sidebar-scrim");
  if (!shell || !sidebar || !toggle || !scrim) return;

  const closeSidebar = () => {
    shell.classList.remove("sidebar-open");
    toggle.setAttribute("aria-expanded", "false");
  };

  toggle.addEventListener("click", () => {
    const isOpen = shell.classList.toggle("sidebar-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });
  scrim.addEventListener("click", closeSidebar);
  sidebar.querySelectorAll("a[href]").forEach((link) => {
    link.addEventListener("click", closeSidebar);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeSidebar();
  });
  const themeToggle = document.getElementById("theme-toggle");
  const themeLabel = document.querySelector(".theme-toggle-label");
  const syncThemeLabel = () => {
    const isDark = document.documentElement.dataset.theme === "dark";
    if (themeLabel) themeLabel.textContent = isDark ? "Light" : "Dark";
    if (themeToggle) themeToggle.setAttribute("aria-label", isDark ? "Switch to light theme" : "Switch to dark theme");
  };
  if (themeToggle) {
    syncThemeLabel();
    themeToggle.addEventListener("click", () => {
      const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem("farmops-theme", next);
      } catch (error) {
        /* private mode: theme applies for this session only */
      }
      syncThemeLabel();
      document.dispatchEvent(new CustomEvent("farmops:theme", { detail: next }));
    });
  }
})();
(() => {
  document.querySelectorAll("form[data-loading-text]").forEach((form) => {
    form.addEventListener("submit", () => {
      if (form.dataset.submitted === "true") return;
      form.dataset.submitted = "true";
      form.setAttribute("aria-busy", "true");
      form.querySelectorAll("button[type=submit]").forEach((button) => {
        if (!button.dataset.originalText) button.dataset.originalText = button.textContent;
        button.textContent = form.dataset.loadingText;
        button.disabled = true;
      });
    });
  });
})();

