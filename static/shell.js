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
})();
